import uuid
import asyncio
import json
from decimal import Decimal
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, UploadFile, File, status
from fastapi.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError, InterfaceError, OperationalError
from sqlalchemy import select, desc, update
from pydantic import BaseModel, ValidationError
import redis.asyncio as redis
import logging

from app.core.database import get_db, async_session_maker
from app.core.redis import get_redis, ChatCache
from app.core.security import verify_token_socket, get_current_user
from app.models.user import User, Wallet
from app.models.chat import Chat, Message
from app.services.llm.factory import LLMFactory
from app.services.llm.router import ModelRouter
from app.services.llm.usage import Usage
from app.services.llm.schema import ChatMessage, Attachment
from app.services.file_processing import process_file


logger = logging.getLogger(__name__)
router = APIRouter()


# Helper Functions for Safe DB Operations

async def safe_db_commit(db: AsyncSession) -> bool:
    """Safely commit a transaction, handling connection errors."""
    try:
        await db.commit()
        return True
    except (SQLAlchemyError, InterfaceError, OperationalError, ConnectionResetError) as e:
        logger.warning(f"Commit failed (connection may be closed): {type(e).__name__}")
        try:
            await db.rollback()
        except Exception:
            pass
        return False
    except Exception as e:
        logger.error(f"Unexpected commit error: {e}")
        try:
            await db.rollback()
        except Exception:
            pass
        return False


async def safe_db_refresh(db: AsyncSession, obj) -> bool:
    """Safely refresh an object, handling connection errors."""
    try:
        await db.refresh(obj)
        return True
    except (SQLAlchemyError, InterfaceError, OperationalError, ConnectionResetError) as e:
        logger.warning(f"Refresh failed (connection may be closed): {type(e).__name__}")
        return False
    except Exception as e:
        logger.error(f"Unexpected refresh error: {e}")
        return False


async def safe_websocket_send(websocket: WebSocket, data: dict) -> bool:
    """Safely send data through WebSocket, handling disconnection."""
    try:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.send_json(data)
            return True
    except (WebSocketDisconnect, ConnectionResetError, RuntimeError) as e:
        logger.debug(f"WebSocket send failed (client disconnected): {type(e).__name__}")
    except Exception as e:
        logger.warning(f"WebSocket send error: {type(e).__name__}: {e}")
    return False


async def safe_websocket_close(websocket: WebSocket, code: int = 1000, reason: str = "") -> None:
    """Safely close WebSocket connection."""
    try:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=code, reason=reason)
    except Exception:
        pass  # Already closed or connection lost


# Schemas

class AttachmentSchema(BaseModel):
    id: Optional[str] = None
    name: str
    type: str
    size: int
    mime_type: Optional[str] = None


class MessageSchema(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    model: Optional[str] = None
    attachments: Optional[List[AttachmentSchema]] = []
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
    attachments: Optional[List[AttachmentSchema]] = []


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


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    redis_client: redis.Redis = Depends(get_redis)
):
    """
    Delete a chat session and its history.
    """
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID format")

    # Fetch Chat and verify ownership
    result = await db.execute(
        select(Chat).where(Chat.id == chat_uuid, Chat.user_id == current_user.id)
    )
    chat = result.scalar_one_or_none()

    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Delete from DB
    await db.delete(chat)
    
    if not await safe_db_commit(db):
        raise HTTPException(status_code=500, detail="Failed to delete chat from database")

    # Clear Redis Cache (History)
    try:
        await redis_client.delete(f"chat:{chat_id}:history")
    except Exception as e:
        logger.error(f"Failed to clear Redis cache for chat {chat_id}: {e}")

    return None



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
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    WebSocket endpoint for real-time chat.
    Uses isolated database sessions for each operation to handle disconnections gracefully.
    """
    await websocket.accept()
    cache = ChatCache(redis_client)
    
    # Track connection state
    is_connected = True
    user: Optional[User] = None
    current_chat: Optional[Chat] = None
    current_chat_id: Optional[uuid.UUID] = None
    wallet_id: Optional[int] = None

    try:
        # 1. Auth & Validation (using isolated session)
        token = websocket.query_params.get("token")
        if not token:
            await safe_websocket_close(websocket, code=1008, reason="Missing token")
            return

        async with async_session_maker() as db:
            user = await verify_token_socket(token, db)
            if not user:
                await safe_websocket_close(websocket, code=1008, reason="Invalid token")
                return
            
            # Store user ID for later use (don't keep the ORM object across sessions)
            user_id = user.id
            user_email = user.email

            # 2. Initial Wallet Check (Read Only)
            result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
            wallet = result.scalar_one_or_none()

            if not wallet or wallet.credits <= Decimal("0.0"):
                await safe_websocket_send(websocket, {"type": "error", "message": "Insufficient credits."})
                await safe_websocket_close(websocket, code=1008)
                return
            
            wallet_id = wallet.id

            # 3. Chat Loading
            if chat_id:
                try:
                    chat_uuid = uuid.UUID(chat_id)
                    result = await db.execute(
                        select(Chat).where(Chat.id == chat_uuid, Chat.user_id == user_id)
                    )
                    existing_chat = result.scalar_one_or_none()
                    if existing_chat:
                        current_chat_id = existing_chat.id
                except ValueError:
                    pass

        logger.info(f"WebSocket connected for user: {user_email}")

        # 4. Main Loop
        while is_connected:
            try:
                # Receive Raw Data
                raw_data = await websocket.receive_text()
                
                # Parse User JSON
                try:
                    payload_data = json.loads(raw_data)
                    payload = UserMessagePayload(**payload_data)
                    
                    if payload.type != "user_message":
                        continue 
                    
                    user_text = payload.content
                    raw_attachments = payload.attachments
                    
                except (json.JSONDecodeError, ValidationError) as e:
                    logger.error(f"Validation error: {e}")
                    await safe_websocket_send(websocket, {"type": "error", "message": "Invalid message format"})
                    continue

                # Process message with isolated database session
                async with async_session_maker() as db:
                    # Lazy Chat Creation
                    if not current_chat_id:
                        # Logic: Title = Text -> First Attachment Name -> "New Chat"
                        if user_text and user_text.strip():
                            title = user_text[:40] + "..." if len(user_text) > 40 else user_text
                        elif raw_attachments:
                            # Use the name of the first attachment
                            first_file = raw_attachments[0]
                            # Handle both Pydantic model (dot notation) or dict (bracket notation) just in case
                            fname = getattr(first_file, 'name', None) or first_file.get('name') or "Attachment"
                            title = f"File: {fname}"
                        else:
                            title = "New Chat"

                        new_chat = Chat(user_id=user_id, title=title)
                        db.add(new_chat)
                        
                        if not await safe_db_commit(db):
                            await safe_websocket_send(websocket, {"type": "error", "message": "Failed to create chat"})
                            continue
                        
                        await safe_db_refresh(db, new_chat)
                        current_chat_id = new_chat.id
                        
                        # Send the new ID back to frontend
                        if not await safe_websocket_send(websocket, {
                            "type": "system",
                            "event": "chat_id",
                            "payload": str(current_chat_id)
                        }):
                            is_connected = False
                            break

                    # Model Routing
                    selected_model = ModelRouter.determine_model(user_text, model)
                    
                    if not await safe_websocket_send(websocket, {
                        "type": "system",
                        "event": "route",
                        "payload": selected_model
                    }):
                        is_connected = False
                        break

                    # Prepare Attachments for LLM
                    current_attachments_for_llm = []
                    
                    if raw_attachments:
                        for att in raw_attachments:
                            # Use dot notation for Pydantic models
                            file_id = att.id 
                            
                            if file_id:
                                # Fetch heavy content from Redis
                                file_data = await cache.get_temp_file(file_id)
                                
                                if file_data:
                                    current_attachments_for_llm.append(Attachment(
                                        type=file_data["type"],
                                        content=file_data["content"],
                                        mime_type=file_data.get("mime_type")
                                    ))

                    # Prepare Metadata for Database
                    metadata_attachments_for_db = []
                    if raw_attachments:
                        for att in raw_attachments:
                            # Use dot notation or .model_dump()/.dict()
                            metadata_attachments_for_db.append({
                                "name": att.name,
                                "type": att.type,
                                "size": att.size,
                                "mime_type": att.mime_type
                            })

                    # Save User Message to DB
                    user_msg = Message(
                        chat_id=current_chat_id,
                        role="user",
                        content=user_text,
                        model=selected_model,
                        attachments=metadata_attachments_for_db,
                    )

                    db.add(user_msg)
                    if not await safe_db_commit(db):
                        await safe_websocket_send(websocket, {"type": "error", "message": "Failed to save message"})

                    # Add to Cache
                    try:
                        await cache.add_message(str(current_chat_id), "user", user_text)
                    except Exception:
                        pass

                    # Context Fetching
                    conversation_history: List[ChatMessage] = []
                    try:
                        conversation_history = await cache.get_history(str(current_chat_id), limit=10)
                    except Exception:
                        pass

                    if not conversation_history:
                        result = await db.execute(
                            select(Message)
                            .where(Message.chat_id == current_chat_id)
                            .order_by(desc(Message.created_at))
                            .limit(10)
                        )
                        msgs = result.scalars().all()
                        for msg in reversed(msgs):
                            conversation_history.append(ChatMessage.from_text(msg.role, msg.content))

                    # Parse Attachments for CURRENT message context
                    current_attachments = []
                    for att in raw_attachments:
                        if "type" in att and "content" in att:
                            current_attachments.append(Attachment(
                                type=att["type"],
                                content=att["content"],
                                mime_type=att.get("mime_type")
                            ))

                    # Append current message WITH attachments to history
                    latest_msg = ChatMessage.from_text("user", user_text)
                    # Use the resolved content from Redis
                    latest_msg.attachments = current_attachments_for_llm
                    
                    # If the last message fetched from history/cache is the same text,
                    # replace it with the rich version containing attachments.
                    if conversation_history and conversation_history[-1].role == "user" and conversation_history[-1].content[0].text == user_text:
                        conversation_history[-1] = latest_msg
                    else:
                        conversation_history.append(latest_msg)


                # AI Generation
                provider = LLMFactory.get_provider(selected_model)
                usage = Usage()
                full_response = ""
                cancel_event = asyncio.Event()

                async def stream_response():
                    nonlocal full_response, is_connected
                    async for chunk in provider.generate_stream(
                        conversation_history,
                        selected_model,
                        usage,
                    ):
                        if cancel_event.is_set():
                            break
                        full_response += chunk
                        
                        if not await safe_websocket_send(websocket, {
                            "type": "content", 
                            "delta": chunk
                        }):
                            is_connected = False
                            cancel_event.set()
                            break

                stream_task = asyncio.create_task(stream_response())

                try:
                    await asyncio.wait_for(stream_task, timeout=60)
                except WebSocketDisconnect:
                    cancel_event.set()
                    stream_task.cancel()
                    is_connected = False
                    # Still need to bill for what was generated
                except asyncio.TimeoutError:
                    cancel_event.set()
                    stream_task.cancel()
                    await safe_websocket_send(websocket, {"type": "error", "message": "Error: Timeout"})
                except asyncio.CancelledError:
                    cancel_event.set()
                    is_connected = False
                except Exception as e:
                    cancel_event.set()
                    stream_task.cancel()
                    err_msg = str(e)
                    await safe_websocket_send(websocket, {"type": "error", "message": f"Error: {err_msg}"})
                    if not full_response:
                        continue

                # Validity Check
                usage.ensure_validity(prompt_text=user_text, completion_text=full_response)
                if not full_response.strip() and usage.total_tokens == 0:
                    if not is_connected:
                        break
                    continue

                # Billing & Atomic Deduction (in new isolated session)
                async with async_session_maker() as db:
                    try:
                        total_cost_to_user = provider.calculate_cost(usage, selected_model)
                        
                        stmt = (
                            update(Wallet)
                            .where(Wallet.user_id == user_id)
                            .values(credits=Wallet.credits - total_cost_to_user)
                            .execution_options(synchronize_session="fetch")
                        )
                        await db.execute(stmt)
                        await safe_db_commit(db)
                        
                        # Check wallet balance
                        result = await db.execute(select(Wallet).where(Wallet.user_id == user_id))
                        updated_wallet = result.scalar_one_or_none()
                        
                        if updated_wallet and updated_wallet.credits < 0:
                            await safe_websocket_send(websocket, {
                                "type": "system",
                                "event": "warning",
                                "payload": "Balance exhausted. Please top up."
                            })

                        # Save AI Message
                        ai_msg = Message(
                            chat_id=current_chat_id,
                            role="ai",
                            content=full_response,
                            model=selected_model,
                            cost=total_cost_to_user,
                            tokens=usage.total_tokens,
                        )
                        db.add(ai_msg)
                        await safe_db_commit(db)

                    except Exception as e:
                        logger.error(f"Error in billing/saving: {e}")
                        # Don't fail completely - response was already sent

                # Cache AI response
                try:
                    await cache.add_message(str(current_chat_id), "ai", full_response)
                except Exception:
                    pass
                
                # Send cost info
                if is_connected:
                    await safe_websocket_send(websocket, {
                        "type": "system",
                        "event": "cost",
                        "payload": str(total_cost_to_user)
                    })

                # Check if we should exit the loop
                if not is_connected:
                    break

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for user: {user_email}")
                is_connected = False
                break
            except ConnectionResetError:
                logger.info(f"Connection reset for user: {user_email} (client closed abruptly)")
                is_connected = False
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected during setup")
    except ConnectionResetError:
        logger.info(f"Connection reset during setup (client closed abruptly)")
    except Exception as e:
        logger.error(f"Critical WebSocket Error: {type(e).__name__}: {e}")
        await safe_websocket_close(websocket, code=1011)
    finally:
        if user:
            logger.info(f"WebSocket cleanup completed for user: {user_email}")
        else:
            logger.info("WebSocket cleanup completed (user not authenticated)")
        

@router.post("/upload")
async def upload_files_for_context(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
    redis_client: redis.Redis = Depends(get_redis) 
):
    processed_metadata = []
    cache = ChatCache(redis_client)
    
    for file in files:
        try:
            # Process the file (Extract text/base64)
            result = await process_file(file)
            
            # Generate a reference ID
            file_id = str(uuid.uuid4())
            
            # Store CONTENT in Redis
            # We store the heavy extracted content here
            file_content_payload = {
                "type": result["type"],
                "content": result["content"],
                "mime_type": result.get("mime_type")
            }
            await cache.save_temp_file(file_id, file_content_payload)

            # Return METADATA + ID to Frontend
            processed_metadata.append({
                "id": file_id,
                "name": result.get("filename", file.filename),
                "type": result["type"],
                "size": file.size,
                "mime_type": file.content_type
            })
            
        except Exception as e:
            logger.error(f"Upload error: {e}")
            processed_metadata.append({
                "filename": file.filename,
                "error": str(e)
            })
            
    return {"files": processed_metadata}