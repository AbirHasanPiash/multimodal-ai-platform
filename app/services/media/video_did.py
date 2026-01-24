import logging
import httpx
from decimal import Decimal
from app.core.config import settings

logger = logging.getLogger(__name__)

class DIDService:
    PRICE_PER_CREDIT = Decimal("0.10") 
    PROFIT_MARGIN = Decimal("4.0")
    USD_TO_CREDITS_RATE = Decimal("10.0")

    def __init__(self):
        raw_key = settings.DID_API_KEY
        
        self.username, self.password = raw_key.split(":", 1)
        self.auth = httpx.BasicAuth(username=self.username, password=self.password)

            
        self.base_url = "https://api.d-id.com"
        self.headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }

    def calculate_cost(self, duration_seconds: int = 15) -> Decimal:
        credits_needed = max(1, (duration_seconds // 15) + 1)
        base_cost = Decimal(credits_needed) * self.PRICE_PER_CREDIT
        user_cost = base_cost * self.PROFIT_MARGIN * self.USD_TO_CREDITS_RATE
        return user_cost.quantize(Decimal("0.000001"))

    async def create_talk(self, source_url: str, audio_url: str) -> str:
        url = f"{self.base_url}/talks"
        
        payload = {
            "source_url": source_url,
            "script": {
                "type": "audio",
                "audio_url": audio_url
            },
            "config": {
                "fluent": True,
                "pad_audio": "0.0",
                "stitch": True
            }
        }

        async with httpx.AsyncClient(auth=self.auth) as client:
            response = await client.post(url, json=payload, headers=self.headers)
            
            if response.status_code not in [200, 201]:
                # Log the full error response for debugging
                logger.error(f"D-ID Create Failed ({response.status_code}): {response.text}")
                raise Exception(f"D-ID Error: {response.text}")
            
            data = response.json()
            return data["id"]

    async def check_status(self, talk_id: str) -> str | None:
        url = f"{self.base_url}/talks/{talk_id}"
        
        async with httpx.AsyncClient(auth=self.auth) as client:
            response = await client.get(url, headers=self.headers)
            
            if response.status_code != 200:
                logger.error(f"D-ID Status Failed ({response.status_code}): {response.text}")
                raise Exception(f"D-ID Status Error: {response.text}")

            data = response.json()
            status = data.get("status")

            if status == "done":
                result_url = data.get("result_url")
                if not result_url:
                    raise Exception("D-ID marked done but no result_url found")
                return result_url
            elif status == "error":
                error_data = data.get("error", {})
                raise Exception(f"D-ID Job Failed: {error_data}")
            
            return None

did_service = DIDService()