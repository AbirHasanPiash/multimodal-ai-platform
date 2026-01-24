import boto3
import logging
from botocore.exceptions import ClientError
from app.core.config import settings

logger = logging.getLogger(__name__)

class StorageService:
    def __init__(self):
        # Initialize boto3 for Cloudflare R2
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY,
            region_name=settings.STORAGE_REGION
        )
        self.bucket = settings.STORAGE_BUCKET_NAME
        self.public_base_url = settings.STORAGE_PUBLIC_URL.rstrip("/")

    def upload_file(self, file_bytes: bytes, destination_path: str, content_type: str) -> str:
        """
        Uploads bytes to R2 and returns the public URL.
        """
        try:
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=destination_path,
                Body=file_bytes,
                ContentType=content_type,
            )
            
            full_url = f"{self.public_base_url}/{destination_path}"
            return full_url

        except ClientError as e:
            logger.error(f"Failed to upload file to storage: {e}")
            raise e

    def delete_file(self, public_url: str):
        """
        Deletes a file from R2 using its public URL.
        """
        if not public_url:
            return

        try:
            # Extract Key from URL
            key = public_url.replace(f"{self.public_base_url}/", "")
            
            self.s3_client.delete_object(
                Bucket=self.bucket, 
                Key=key
            )
            logger.info(f"Deleted file from storage: {key}")
            
        except ClientError as e:
            logger.error(f"Failed to delete file from storage: {e}")
            pass

# Singleton instance
storage = StorageService()