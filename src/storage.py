import logging
import os
from pathlib import Path
from typing import Optional
from qcloud_cos import CosConfig
from qcloud_cos import CosS3Client
from .config import settings

logger = logging.getLogger(__name__)

class TencentCOSClient:
    def __init__(self):
        self.enabled = False
        if settings.COS_SECRET_ID and settings.COS_SECRET_KEY and settings.COS_REGION and settings.COS_BUCKET:
            try:
                self.config = CosConfig(
                    Region=settings.COS_REGION, 
                    SecretId=settings.COS_SECRET_ID, 
                    SecretKey=settings.COS_SECRET_KEY,
                    Token=None, 
                    Scheme='https'
                )
                self.client = CosS3Client(self.config)
                self.bucket = settings.COS_BUCKET
                self.enabled = True
                logger.info("Tencent COS Client initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize Tencent COS Client: {e}")
        else:
            logger.warning("Tencent COS credentials not fully configured. Image upload disabled.")

    def upload_file(self, file_path: Path, key: Optional[str] = None) -> Optional[str]:
        """
        Uploads a file to COS and returns the public URL.
        """
        if not self.enabled:
            logger.error("Attempted to upload but COS client is not enabled.")
            return None

        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        # Determine object key
        if not key:
            # Use relative path from project root or just filename with a prefix
            # Let's try to keep it organized: cineflow_uploads/{filename}
            # Or use MD5 hash to deduplicate? For now, simple filename.
            key = f"cineflow_assets/{file_path.name}"
        
        try:
            logger.info(f"Uploading {file_path} to COS as {key}...")
            response = self.client.upload_file(
                Bucket=self.bucket,
                LocalFilePath=str(file_path),
                Key=key,
                EnableMD5=False,
                ProgressCallback=None
            )
            
            # Construct URL
            if settings.COS_CUSTOM_DOMAIN:
                # Assuming custom domain doesn't end with slash, key doesn't start with slash
                domain = settings.COS_CUSTOM_DOMAIN.rstrip('/')
                url = f"{domain}/{key}"
            else:
                # Standard URL: https://{Bucket}.cos.{Region}.myqcloud.com/{Key}
                url = f"https://{self.bucket}.cos.{settings.COS_REGION}.myqcloud.com/{key}"
            
            logger.info(f"Upload successful. URL: {url}")
            return url
            
        except Exception as e:
            logger.error(f"Failed to upload file to COS: {e}")
            return None
