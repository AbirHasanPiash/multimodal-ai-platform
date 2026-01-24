import asyncio
import uuid
from celery import Celery
from app.core.config import settings
from app.core.database import async_session_maker
from app.models import GeneratedAudio, GeneratedImage, User, Wallet, GeneratedVideo
from app.services.media.image_openai import image_service
from sqlalchemy.future import select
import httpx
from app.services.media.video_did import did_service
from app.services.storage import storage
from app.services.media.tts_google import tts_service

celery_app = Celery("worker", broker=settings.REDIS_URL, backend=settings.REDIS_URL)

@celery_app.task(name="generate_tts_task")
def generate_tts_task(
    text: str, 
    chat_id: str, 
    message_id: str, 
    user_id: str, 
    cost: float,
    voice_name: str = "en-US-Neural2-F"
):
    """
    Background task to generate TTS audio with a specific voice.
    """
    async def _async_process():
        # Pass the selected voice to Google Service
        public_url = await tts_service.generate_audio(text, voice_name=voice_name)
        
        async with async_session_maker() as db:
            new_audio = GeneratedAudio(
                user_id=uuid.UUID(user_id),
                storage_path=public_url.split('/')[-1],
                public_url=public_url,
                text_prompt=text[:500],
                source_message_id=uuid.UUID(message_id) if message_id else None,
                provider="google",
                voice_name=voice_name,
                cost=cost
            )
            db.add(new_audio)
            await db.commit()
            
        return public_url

    loop = asyncio.get_event_loop()
    try:
        audio_url = loop.run_until_complete(_async_process())
        return {"status": "success", "audio_url": audio_url}
    except Exception as e:
        return {"status": "failed", "error": str(e)}
    


@celery_app.task(name="generate_image_task")
def generate_image_task(
    prompt: str,
    user_id: str,
    model: str,
    size: str = "1024x1024",
    quality: str = "medium",
    reference_image_url: str = None
):
    """
    Background task to generate Image, Upload to R2, and Charge Wallet.
    """
    async def _async_process():
        # Calculate Cost
        cost = image_service.calculate_cost(model, quality, size)
        
        # Generate
        result = await image_service.generate_and_upload(
            prompt=prompt,
            model=model,
            size=size,
            quality=quality,
            user_id=user_id,
            reference_image_url=reference_image_url
        )
        
        # DB Transaction
        async with async_session_maker() as db:
            new_image = GeneratedImage(
                user_id=uuid.UUID(user_id),
                storage_path=result['public_url'].split('/')[-1],
                public_url=result['public_url'],
                prompt=prompt,
                revised_prompt=result['revised_prompt'],
                model=model,
                size=size,
                quality=quality,
                cost=cost,
                reference_image_url=reference_image_url
            )
            db.add(new_image)
            
            # Deduct from Wallet
            result_wallet = await db.execute(select(Wallet).where(Wallet.user_id == uuid.UUID(user_id)))
            wallet = result_wallet.scalars().first()
            
            if wallet:
                wallet.credits -= cost
                if wallet.credits < 0:
                    raise Exception("Insufficient credits in wallet.")
                db.add(wallet)
            
            await db.commit()
            
        return result['public_url']

    loop = asyncio.get_event_loop()
    try:
        image_url = loop.run_until_complete(_async_process())
        return {"status": "success", "image_url": image_url}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@celery_app.task(name="generate_avatar_task")
def generate_avatar_task(
    script_text: str,
    voice_name: str,
    avatar_url: str,
    user_id: str,
    video_db_id: str
):
    async def _async_process():
        async with async_session_maker() as db:
            stmt = select(GeneratedVideo).where(GeneratedVideo.id == uuid.UUID(video_db_id))
            video_record = (await db.execute(stmt)).scalar_one()

            try:
                # Generate TTS
                audio_url = await tts_service.generate_audio(script_text, voice_name=voice_name)
                video_record.source_audio_url = audio_url
                
                # Smart Avatar Handling
                clean_avatar_url = avatar_url

                my_storage_domain = settings.STORAGE_PUBLIC_URL.rstrip('/')
                
                if avatar_url.startswith(my_storage_domain):
                    pass 
                else:
                    # Sanitize external/dirty URL
                    async with httpx.AsyncClient() as client:
                        img_resp = await client.get(avatar_url)
                        img_resp.raise_for_status()
                        
                        clean_avatar_filename = f"avatars/{user_id}/{uuid.uuid4()}.png"
                        clean_avatar_url = storage.upload_file(
                            file_bytes=img_resp.content,
                            destination_path=clean_avatar_filename,
                            content_type="image/png"
                        )
                
                # Update DB
                video_record.avatar_image_url = clean_avatar_url
                db.add(video_record)
                await db.commit()

                # Trigger D-ID Generation
                job_id = await did_service.create_talk(
                    source_url=clean_avatar_url,
                    audio_url=audio_url
                )
                
                video_record.external_job_id = job_id
                video_record.status = "processing_external"
                db.add(video_record)
                await db.commit()

                # Poll for Completion
                final_video_url = None
                for _ in range(40):
                    await asyncio.sleep(3)
                    final_video_url = await did_service.check_status(job_id)
                    if final_video_url:
                        break
                
                if not final_video_url:
                    raise Exception("Timeout waiting for D-ID generation")

                # Download & Finalize
                async with httpx.AsyncClient() as client:
                    video_bytes = (await client.get(final_video_url)).content

                r2_path = f"generated_videos/{user_id}/{uuid.uuid4()}.mp4"
                public_url = storage.upload_file(video_bytes, r2_path, "video/mp4")

                video_record.status = "completed"
                video_record.public_url = public_url
                video_record.storage_path = r2_path
                db.add(video_record)
                await db.commit()

            except Exception as e:
                video_record.status = "failed"
                video_record.error_message = str(e)
                db.add(video_record)
                await db.commit()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_async_process())