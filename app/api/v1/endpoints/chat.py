import uuid
import asyncio
import json
from decimal import Decimal
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update
from pydantic import BaseModel, ValidationError
import redis.asyncio as redis

from app.core.database import get_db
from app.core.redis import get_redis, ChatCache
from app.core.security import verify_token_socket, get_current_user
from app.models.user import User, Wallet
from app.models.chat import Chat, Message
from app.services.llm.factory import LLMFactory
from app.services.llm.router import ModelRouter
from app.services.llm.usage import Usage
from app.services.llm.schema import ChatMessage

router = APIRouter()

# Schemas
class MessageSchema(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    model: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ChatSchema(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime

    class Config:
        from_attributes = True

class UserMessagePayload(BaseModel):
    type: str
    content: str

# HTTP Endpoints (GETs)
@router.get("/history/{chat_id}", response_model=List[MessageSchema])
async def get_chat_history(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        return []

    result = await db.execute(
        select(Chat).where(Chat.id == chat_uuid, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_uuid)
        .order_by(Message.created_at.asc())
    )
    return result.scalars().all()

@router.get("/list", response_model=List[ChatSchema])
async def get_user_chats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Chat)
        .where(Chat.user_id == current_user.id)
        .order_by(desc(Chat.created_at))
    )
    return result.scalars().all()

# WebSocket Endpoint
@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    model: str = "auto",
    chat_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    await websocket.accept()
    cache = ChatCache(redis_client)

    try:
        # 1. Auth & Validation
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=1008, reason="Missing token")
            return

        user = await verify_token_socket(token, db)
        if not user:
            await websocket.close(code=1008, reason="Invalid token")
            return

        # 2. Initial Wallet Check (Read Only)
        # We don't lock here, we just check if they are already at 0.
        result = await db.execute(select(Wallet).where(Wallet.user_id == user.id))
        wallet = result.scalar_one_or_none()

        if not wallet or wallet.credits <= Decimal("0.0"):
            await websocket.send_json({"type": "error", "message": "Insufficient credits."})
            await websocket.close(code=1008)
            return

        # 3. Chat Loading
        current_chat: Optional[Chat] = None
        if chat_id:
            try:
                chat_uuid = uuid.UUID(chat_id)
                result = await db.execute(
                    select(Chat).where(Chat.id == chat_uuid, Chat.user_id == user.id)
                )
                current_chat = result.scalar_one_or_none()
            except ValueError:
                pass

        # 4. Main Loop
        while True:
            # Receive Raw Data
            raw_data = await websocket.receive_text()
            
            # Parse User JSON
            try:
                payload_data = json.loads(raw_data)
                payload = UserMessagePayload(**payload_data)
                
                if payload.type != "user_message":
                    continue 
                
                user_text = payload.content
            except (json.JSONDecodeError, ValidationError):
                await websocket.send_json({"type": "error", "message": "Invalid message format"})
                continue

            # Lazy Chat Creation
            if not current_chat:
                title = user_text[:40] + "..." if len(user_text) > 40 else user_text
                current_chat = Chat(user_id=user.id, title=title)
                db.add(current_chat)
                await db.commit()
                await db.refresh(current_chat)
                
                await websocket.send_json({
                    "type": "system",
                    "event": "chat_id",
                    "payload": str(current_chat.id)
                })

            # Model Routing
            selected_model = ModelRouter.determine_model(user_text, model)
            
            await websocket.send_json({
                "type": "system",
                "event": "route",
                "payload": selected_model
            })

            # Save User Message to DB
            user_msg = Message(
                chat_id=current_chat.id,
                role="user",
                content=user_text,
                model=selected_model,
            )
            db.add(user_msg)
            await db.commit()

            # Add to Cache
            try:
                await cache.add_message(str(current_chat.id), "user", user_text)
            except Exception:
                pass

            # Context Fetching
            conversation_history: List[ChatMessage] = []
            try:
                conversation_history = await cache.get_history(str(current_chat.id), limit=10)
            except Exception:
                pass

            if not conversation_history:
                result = await db.execute(
                    select(Message)
                    .where(Message.chat_id == current_chat.id)
                    .order_by(desc(Message.created_at))
                    .limit(10)
                )
                msgs = result.scalars().all()
                for msg in reversed(msgs):
                    conversation_history.append(ChatMessage.from_text(msg.role, msg.content))

            # AI Generation
            provider = LLMFactory.get_provider(selected_model)
            usage = Usage()
            full_response = ""
            cancel_event = asyncio.Event()

            async def stream_response():
                nonlocal full_response
                async for chunk in provider.generate_stream(
                    conversation_history,
                    selected_model,
                    usage,
                ):
                    if cancel_event.is_set():
                        break
                    full_response += chunk
                    
                    await websocket.send_json({
                        "type": "content", 
                        "delta": chunk
                    })

            stream_task = asyncio.create_task(stream_response())

            try:
                await asyncio.wait_for(stream_task, timeout=60)
            except (WebSocketDisconnect, asyncio.TimeoutError, Exception) as e:
                cancel_event.set()
                stream_task.cancel()
                err_msg = str(e) if not isinstance(e, WebSocketDisconnect) else "Disconnected"
                if not isinstance(e, WebSocketDisconnect):
                    await websocket.send_json({"type": "error", "message": f"Error: {err_msg}"})
                # We do NOT break here immediately, we must calculate cost for what was generated so far
                if not full_response:
                    if isinstance(e, WebSocketDisconnect): raise
                    continue

            # Validity Check
            usage.ensure_validity(prompt_text=user_text, completion_text=full_response)
            if not full_response.strip() and usage.total_tokens == 0:
                continue

            # 5. Billing & Atomic Deduction
            # provider.calculate_cost now includes the 4X Margin and returns Decimal
            total_cost_to_user = provider.calculate_cost(usage, selected_model)
            
            stmt = (
                update(Wallet)
                .where(Wallet.user_id == user.id)
                .values(credits=Wallet.credits - total_cost_to_user)
                .execution_options(synchronize_session="fetch")
            )
            await db.execute(stmt)
            await db.commit()
            
            # Refresh local wallet object to check for negative balance handling
            await db.refresh(wallet)
            
            if wallet.credits < 0:
                 await websocket.send_json({
                    "type": "system",
                    "event": "warning",
                    "payload": "Balance exhausted. Please top up."
                })

            # Save AI Message
            ai_msg = Message(
                chat_id=current_chat.id,
                role="ai",
                content=full_response,
                model=selected_model,
                cost=total_cost_to_user, # Storing the Price (with Margin)
                tokens=usage.total_tokens,
            )
            db.add(ai_msg)
            await db.commit()

            try:
                await cache.add_message(str(current_chat.id), "ai", full_response)
            except Exception:
                pass
            
            await websocket.send_json({
                "type": "system",
                "event": "cost",
                "payload": str(total_cost_to_user)
            })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        # print(f"CRITICAL WebSocket Error: {e}")
        try:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=1011)
        except Exception:
            pass