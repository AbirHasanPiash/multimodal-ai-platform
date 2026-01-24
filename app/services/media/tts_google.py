import os
os.environ["GRPC_DNS_RESOLVER"] = "native"
import uuid
import logging
from decimal import Decimal
from google.cloud import texttospeech
from google.oauth2 import service_account
from app.core.config import settings
from app.services.storage import storage

logger = logging.getLogger(__name__)

class GoogleTTSService:
    PROVIDER_COST_PER_CHAR = Decimal("0.000016")

    PROFIT_MARGIN = Decimal("4.0")
    USD_TO_CREDITS_RATE = Decimal("10.0")

    def __init__(self):
        # Authenticate using the JSON key file path from env
        self.credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
        
        
        # Check if path is set and file exists
        if self.credentials_path and os.path.exists(self.credentials_path):
            self.credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path
            )
            self.client = texttospeech.TextToSpeechClient(credentials=self.credentials)
        else:
            # Helpful error message if file is missing
            if self.credentials_path:
                logger.error(f"Credentials file not found at: {self.credentials_path}")
            else:
                logger.warning("GOOGLE_APPLICATION_CREDENTIALS not set in .env")
                
            self.client = texttospeech.TextToSpeechClient()

    def calculate_cost(self, text: str) -> Decimal:
        """
        Calculates the final cost in CREDITS for the user.
        Formula: (Chars * ProviderPrice * Margin) * ExchangeRate
        """
        char_count = len(text)
        cost_usd = Decimal(char_count) * self.PROVIDER_COST_PER_CHAR
        price_to_user_usd = cost_usd * self.PROFIT_MARGIN
        total_credits = price_to_user_usd * self.USD_TO_CREDITS_RATE
        
        # Round to 6 decimal places
        return total_credits.quantize(Decimal("0.000001"))

    async def generate_audio(self, text: str, voice_name: str = "en-US-Neural2-F") -> str:
        """
        Generates MP3 audio from text, uploads to Storage, and returns public URL.
        """
        try:
            # Configure the request
            synthesis_input = texttospeech.SynthesisInput(text=text)

            # Build the voice request
            voice = texttospeech.VoiceSelectionParams(
                language_code="en-US",
                name=voice_name
            )

            # Select the type of audio file you want returned
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,
                pitch=0.0
            )

            # Call Google API
            response = self.client.synthesize_speech(
                input=synthesis_input, 
                voice=voice, 
                audio_config=audio_config
            )

            # Upload to R2 Storage
            # Generate a unique filename
            filename = f"tts/{uuid.uuid4()}.mp3"
            
            # The response.audio_content is bytes
            public_url = storage.upload_file(
                file_bytes=response.audio_content,
                destination_path=filename,
                content_type="audio/mpeg"
            )
            
            return public_url

        except Exception as e:
            logger.error(f"Google TTS generation failed: {e}")
            raise e

# Singleton instance
tts_service = GoogleTTSService()