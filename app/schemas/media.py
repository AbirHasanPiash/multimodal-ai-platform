from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class GeneratedAudioResponse(BaseModel):
    id: UUID
    public_url: str
    text_prompt: str
    voice_name: Optional[str]
    provider: str
    cost: float
    created_at: datetime
    
    class Config:
        from_attributes = True


class ImageGenerationRequest(BaseModel):
    prompt: str
    model: str = "gpt-image-1.5"
    size: str = "1024x1024"
    quality: str = "standard"
    reference_image_url: Optional[str] = None
    n: int = 1

class GeneratedImageResponse(BaseModel):
    id: UUID
    public_url: str
    prompt: str
    reference_image_url: Optional[str]
    model: str 
    size: str
    quality: str
    cost: float
    created_at: datetime
    
    class Config:
        from_attributes = True


class VideoGenerationRequest(BaseModel):
    text: str
    voice_name: str = "en-US-Neural2-F"
    avatar_url: str
    provider: str = "d-id"


class GeneratedVideoResponse(BaseModel):
    id: UUID
    public_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    status: str
    text_prompt: str = ""
    avatar_image_url: str 
    cost: float
    created_at: datetime
    
    class Config:
        from_attributes = True