import redis.asyncio as redis
import json
from typing import List
from app.core.config import settings
from app.services.llm.schema import ChatMessage 

REDIS_URL = settings.REDIS_URL

async def get_redis():
    """Dependency to get Redis connection"""
    client = redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()

class ChatCache:
    """Helper to manage Chat History in Redis"""
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.ttl = 3600  # Cache expires in 1 hour

    async def add_message(self, chat_id: str, role: str, content: str):
        key = f"chat:{chat_id}:history"
        # We serialize to JSON for storage
        msg = json.dumps({"role": role, "content": content})
        await self.redis.rpush(key, msg)
        await self.redis.expire(key, self.ttl)

    async def get_history(self, chat_id: str, limit: int = 10) -> List[ChatMessage]:
        key = f"chat:{chat_id}:history"
        raw_messages = await self.redis.lrange(key, -limit, -1)
        
        # Transformation Logic: JSON String -> Dict -> ChatMessage Object
        history_objects = []
        for m in raw_messages:
            data = json.loads(m)
            obj = ChatMessage.from_text(role=data["role"], content=data["content"])
            history_objects.append(obj)
            
        return history_objects
    
    async def save_temp_file(self, file_id: str, file_data: dict):
        """
        Stores file content (base64 or text) in Redis with an expiration.
        """
        key = f"temp_file:{file_id}"
        await self.redis.setex(
            key,
            self.ttl,
            json.dumps(file_data)
        )

    async def get_temp_file(self, file_id: str) -> dict | None:
        """
        Retrieves file content by ID.
        """
        key = f"temp_file:{file_id}"
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None