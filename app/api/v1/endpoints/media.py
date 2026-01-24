import uuid
import logging
from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, Wallet
from app.models.chat import Message
from app.models.media import GeneratedAudio, GeneratedVideo, GeneratedImage
from app.services.media.video_did import did_service
from app.workers.tasks import generate_tts_task, generate_image_task, generate_avatar_task
from app.services.media.tts_google import tts_service
from app.schemas.media import GeneratedAudioResponse, ImageGenerationRequest, GeneratedImageResponse, VideoGenerationRequest, GeneratedVideoResponse
from app.services.media.image_openai import image_service
from app.services.storage import storage


router = APIRouter()
logger = logging.getLogger(__name__)


# AUDIO / TTS ENDPOINTS

@router.get("/list", response_model=List[GeneratedAudioResponse])
async def list_generated_audio(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(GeneratedAudio)
        .where(GeneratedAudio.user_id == current_user.id)
        .order_by(GeneratedAudio.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.delete("/audio/{audio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_audio(
    audio_id: str = Path(..., title="The ID of the audio to delete"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete generated audio from DB and Storage.
    """
    try:
        audio_uuid = uuid.UUID(audio_id)
    except ValueError:
        raise HTTPException(400, "Invalid UUID")

    result = await db.execute(
        select(GeneratedAudio).where(GeneratedAudio.id == audio_uuid, GeneratedAudio.user_id == current_user.id)
    )
    audio = result.scalar_one_or_none()

    if not audio:
        raise HTTPException(404, "Audio not found")

    # Delete from Storage (R2)
    if audio.public_url:
        storage.delete_file(audio.public_url)

    # Delete from DB
    await db.delete(audio)
    await db.commit()
    return None


@router.post("/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_audio_direct(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    text = payload.get("text", "").strip()
    voice_name = payload.get("voice_name", "en-US-Neural2-F")
    
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")

    estimated_cost = tts_service.calculate_cost(text)
    
    wallet_result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
    wallet = wallet_result.scalar_one_or_none()
    
    if not wallet or wallet.credits < estimated_cost:
         raise HTTPException(status_code=402, detail="Insufficient credits")
    
    wallet.credits -= estimated_cost
    db.add(wallet)
    await db.commit()

    task = generate_tts_task.delay(
        text=text,
        chat_id=str(uuid.uuid4()),
        message_id=None,
        user_id=str(current_user.id),
        cost=float(estimated_cost),
        voice_name=voice_name
    )
    
    return {"status": "processing", "task_id": task.id}


@router.post("/tts/{message_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_tts_generation(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    try:
        msg_uuid = uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    result = await db.execute(
        select(Message)
        .options(selectinload(Message.chat))
        .where(Message.id == msg_uuid)
    )
    message = result.scalar_one_or_none()

    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.chat.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You do not have permission to access this message"
        )

    audio_result = await db.execute(
        select(GeneratedAudio).where(GeneratedAudio.source_message_id == msg_uuid)
    )
    existing_audio = audio_result.scalar_one_or_none()

    if existing_audio:
        return {
            "status": "exists",
            "message_id": str(msg_uuid),
            "audio_url": existing_audio.public_url,
            "info": "Audio already generated."
        }

    clean_text = message.content.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="Message has no text")
    if len(clean_text) > 4096:
        clean_text = clean_text[:4096]

    estimated_cost = tts_service.calculate_cost(clean_text)

    wallet_result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
    wallet = wallet_result.scalar_one_or_none()

    if not wallet:
        raise HTTPException(status_code=400, detail="User has no wallet configured")

    if wallet.credits < estimated_cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Cost: {estimated_cost}, Balance: {wallet.credits}"
        )

    wallet.credits -= estimated_cost
    db.add(wallet)
    await db.commit()

    task = generate_tts_task.delay(
        text=clean_text,
        chat_id=str(message.chat.id),
        message_id=str(message.id),
        user_id=str(current_user.id),
        cost=float(estimated_cost),
        voice_name="en-US-Neural2-F"
    )

    return {
        "status": "processing",
        "task_id": task.id,
        "cost_deducted": float(estimated_cost),
        "message": "TTS generation started."
    }


# IMAGE ENDPOINTS

@router.get("/images/list", response_model=List[GeneratedImageResponse])
async def list_generated_images(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(GeneratedImage)
        .where(GeneratedImage.user_id == current_user.id)
        .order_by(GeneratedImage.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    image_id: str = Path(..., title="The ID of the image to delete"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete generated image from DB and Storage.
    """
    try:
        img_uuid = uuid.UUID(image_id)
    except ValueError:
        raise HTTPException(400, "Invalid UUID")

    result = await db.execute(
        select(GeneratedImage).where(GeneratedImage.id == img_uuid, GeneratedImage.user_id == current_user.id)
    )
    image = result.scalar_one_or_none()

    if not image:
        raise HTTPException(404, "Image not found")

    # Delete from Storage (R2)
    if image.public_url:
        storage.delete_file(image.public_url)

    # Delete from DB
    await db.delete(image)
    await db.commit()
    return None


@router.post("/generate-image", status_code=202)
async def generate_image(
    request: ImageGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if request.reference_image_url and request.model != "gpt-image-1.5":
         raise HTTPException(
            status_code=400,
            detail="Reference images are only supported for gpt-image-1.5 model."
        )

    estimated_cost = image_service.calculate_cost(
        model=request.model,
        quality=request.quality, 
        size=request.size
    )

    stmt = select(Wallet).where(Wallet.user_id == current_user.id)
    result = await db.execute(stmt)
    wallet = result.scalars().first()

    if not wallet or wallet.credits < estimated_cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Cost: {estimated_cost}, Balance: {wallet.credits if wallet else 0}"
        )

    task = generate_image_task.delay(
        prompt=request.prompt,
        user_id=str(current_user.id),
        model=request.model,
        size=request.size,
        quality=request.quality,
        reference_image_url=request.reference_image_url
    )

    return {
        "task_id": task.id,
        "status": "processing",
        "estimated_cost": estimated_cost,
        "message": "Image generation started."
    }


# VIDEO / AVATAR ENDPOINTS

@router.get("/videos/list", response_model=List[GeneratedVideoResponse])
async def list_generated_videos(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(GeneratedVideo)
        .where(GeneratedVideo.user_id == current_user.id)
        .order_by(GeneratedVideo.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.delete("/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_video(
    video_id: str = Path(..., title="The ID of the video to delete"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete generated video from DB and Storage.
    Also deletes the specific source audio file generated for this video from Storage.
    """
    try:
        vid_uuid = uuid.UUID(video_id)
    except ValueError:
        raise HTTPException(400, "Invalid UUID")

    # Fetch the Video
    result = await db.execute(
        select(GeneratedVideo).where(GeneratedVideo.id == vid_uuid, GeneratedVideo.user_id == current_user.id)
    )
    video = result.scalar_one_or_none()

    if not video:
        raise HTTPException(404, "Video not found")

    # Delete the Video file from R2
    if video.public_url and video.public_url != "pending":
        storage.delete_file(video.public_url)
    
    # Delete the specific Audio file used for this video from R2
    if video.source_audio_url and video.source_audio_url != "pending":
        storage.delete_file(video.source_audio_url)

    # Delete Video Record from DB
    await db.delete(video)
    await db.commit()
    
    return None


@router.post("/upload", status_code=200)
async def upload_media_asset(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(400, detail="Invalid file type. Only JPEG, PNG, or WebP allowed.")
    
    file_bytes = await file.read()
    
    file_ext = file.filename.split('.')[-1] if '.' in file.filename else "png"
    filename = f"uploads/{current_user.id}/{uuid.uuid4()}.{file_ext}"
    
    public_url = storage.upload_file(
        file_bytes=file_bytes,
        destination_path=filename,
        content_type=file.content_type
    )
    
    return {"public_url": public_url}


@router.post("/generate-avatar", status_code=202)
async def generate_avatar(
    request: VideoGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    estimated_cost = did_service.calculate_cost(duration_seconds=15)

    wallet = (await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))).scalar_one_or_none()

    if not wallet or wallet.credits < estimated_cost:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Insufficient credits. Required: {estimated_cost}"
        )

    new_video = GeneratedVideo(
        user_id=current_user.id,
        storage_path="pending",
        public_url="pending",
        script_text=request.text,
        source_audio_url="pending",
        avatar_image_url=request.avatar_url,
        provider="d-id",
        model="talks",
        cost=estimated_cost,
        status="processing"
    )
    db.add(new_video)
    
    wallet.credits -= estimated_cost
    db.add(wallet)
    
    await db.commit()
    await db.refresh(new_video)

    task = generate_avatar_task.delay(
        script_text=request.text,
        voice_name=request.voice_name,
        avatar_url=request.avatar_url,
        user_id=str(current_user.id),
        video_db_id=str(new_video.id)
    )

    return {
        "task_id": task.id,
        "video_id": new_video.id,
        "status": "processing",
        "estimated_cost": estimated_cost,
        "message": "Avatar generation started with D-ID."
    }