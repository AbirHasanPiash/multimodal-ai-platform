import uuid
import logging
import httpx
from decimal import Decimal
from openai import AsyncOpenAI
from app.core.config import settings
from app.services.storage import storage

logger = logging.getLogger(__name__)

class OpenAIImageService:
    PRICING_TABLE = {
        "gpt-image-1.5": {
            "low": {
                "1024x1024": Decimal("0.009"),
                "1024x1536": Decimal("0.013"),
                "1536x1024": Decimal("0.013")
            },
            "medium": {
                "1024x1024": Decimal("0.034"),
                "1024x1536": Decimal("0.050"),
                "1536x1024": Decimal("0.050")
            },
            "high": {
                "1024x1024": Decimal("0.133"),
                "1024x1536": Decimal("0.200"),
                "1536x1024": Decimal("0.200")
            }
        },
        "dall-e-3": {
            "standard": {
                "1024x1024": Decimal("0.040"),
                "1024x1536": Decimal("0.080"),
                "1536x1024": Decimal("0.080")
            },
            "hd": {
                "1024x1024": Decimal("0.080"),
                "1024x1536": Decimal("0.120"),
                "1536x1024": Decimal("0.120")
            }
        }
    }
    
    PROFIT_MARGIN = Decimal("4.0")
    USD_TO_CREDITS_RATE = Decimal("10.0")

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    def calculate_cost(self, model: str, quality: str, size: str) -> Decimal:
        """
        Calculates User Cost in Credits.
        Handles both 'standard/hd' (dall-e-3) and 'low/medium/high' (gpt-image-1.5).
        """
        model_pricing = self.PRICING_TABLE.get(model)
        
        # Fallback to defaults if model not found
        if not model_pricing:
            model_pricing = self.PRICING_TABLE["gpt-image-1.5"]

        # Default quality fallback depends on model
        default_quality = "standard" if model == "dall-e-3" else "medium"
        quality_pricing = model_pricing.get(quality, model_pricing.get(default_quality))
        
        # Get base price
        base_price = quality_pricing.get(size, Decimal("0.040"))
        
        user_cost = base_price * self.PROFIT_MARGIN * self.USD_TO_CREDITS_RATE
        return user_cost.quantize(Decimal("0.000001"))

    async def generate_and_upload(
        self, 
        prompt: str, 
        model: str, 
        size: str, 
        quality: str, 
        user_id: str,
        reference_image_url: str = None
    ) -> dict:
        try:
            params = {
                "model": model,
                "prompt": prompt,
                "size": size,
                "quality": quality,
                "n": 1,
            }

            # Logic for Reference Image (GPT-Image-1.5 only)
            if model == "gpt-image-1.5" and reference_image_url:
                # Download the reference image from the provided URL
                async with httpx.AsyncClient() as dl_client:
                    ref_response = await dl_client.get(reference_image_url)
                    ref_response.raise_for_status()
                    params["image"] = ref_response.content 
            
            # Call OpenAI
            response = await self.client.images.generate(**params)
            
            image_data = response.data[0]
            temp_url = image_data.url
            revised_prompt = image_data.revised_prompt or prompt

            # Download Generated Image
            async with httpx.AsyncClient() as http_client:
                img_response = await http_client.get(temp_url)
                img_response.raise_for_status()
                file_bytes = img_response.content

            # Upload to R2
            filename = f"generated_images/{user_id}/{uuid.uuid4()}.png"
            public_url = storage.upload_file(
                file_bytes=file_bytes,
                destination_path=filename,
                content_type="image/png"
            )

            return {
                "public_url": public_url,
                "revised_prompt": revised_prompt
            }

        except Exception as e:
            logger.error(f"Image Generation Failed: {e}")
            raise e

image_service = OpenAIImageService()