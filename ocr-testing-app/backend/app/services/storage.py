"""
Amazon S3 storage service.
"""
import uuid
from typing import Optional, BinaryIO
from pathlib import Path

import boto3
from botocore.config import Config

from app.config import get_settings

settings = get_settings()

_s3_client = None


def _get_client():
    """Get or create the S3 client singleton."""
    global _s3_client
    if _s3_client is None:
        kwargs = {"region_name": settings.aws_default_region}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        _s3_client = boto3.client("s3", **kwargs)
    return _s3_client


class StorageService:
    """Service for Amazon S3 storage operations."""

    def __init__(self):
        """Initialize S3 client."""
        self.client = _get_client()
        self.bucket_name = settings.s3_bucket

    def _extract_key(self, storage_path: str) -> str:
        """Extract the S3 key from a path (handles legacy gs:// and s3:// prefixes)."""
        if storage_path.startswith("gs://"):
            parts = storage_path.split("/", 3)
            return parts[3] if len(parts) > 3 else ""
        if storage_path.startswith("s3://"):
            parts = storage_path.split("/", 3)
            return parts[3] if len(parts) > 3 else ""
        return storage_path

    async def upload_form(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str = "image/png"
    ) -> str:
        """Upload a form template to storage. Returns the S3 key."""
        form_id = str(uuid.uuid4())
        extension = Path(filename).suffix or ".png"
        key = f"forms/{form_id}{extension}"
        self.client.upload_fileobj(
            file, self.bucket_name, key,
            ExtraArgs={"ContentType": content_type}
        )
        return key

    async def upload_synthetic_document(
        self,
        file: BinaryIO,
        batch_id: str,
        document_id: str,
        content_type: str = "image/png"
    ) -> str:
        """Upload a synthetic document to storage. Returns the S3 key."""
        key = f"batches/{batch_id}/{document_id}.png"
        self.client.upload_fileobj(
            file, self.bucket_name, key,
            ExtraArgs={"ContentType": content_type}
        )
        return key

    async def upload_bytes(
        self,
        data: bytes,
        blob_name: str,
        content_type: str = "image/png"
    ) -> str:
        """Upload bytes to storage. Returns the S3 key."""
        self.client.put_object(
            Bucket=self.bucket_name,
            Key=blob_name,
            Body=data,
            ContentType=content_type,
        )
        return blob_name

    async def download_file(self, storage_path: str) -> bytes:
        """Download a file from storage."""
        key = self._extract_key(storage_path)
        response = self.client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()

    async def get_signed_url(
        self,
        storage_path: str,
        expiration_minutes: int = 60
    ) -> str:
        """Generate a presigned URL for temporary access to a file."""
        key = self._extract_key(storage_path)
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": key},
            ExpiresIn=expiration_minutes * 60,
        )
        return url

    async def copy_file(self, source_path: str, dest_blob_name: str) -> str:
        """Copy a file within the same bucket (server-side). Returns the S3 key."""
        source_key = self._extract_key(source_path)
        self.client.copy_object(
            Bucket=self.bucket_name,
            CopySource={"Bucket": self.bucket_name, "Key": source_key},
            Key=dest_blob_name,
        )
        return dest_blob_name

    async def delete_file(self, storage_path: str) -> bool:
        """Delete a file from storage."""
        try:
            key = self._extract_key(storage_path)
            self.client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
        except Exception:
            return False

    async def delete_batch_folder(self, batch_id: str) -> int:
        """Delete all files in a batch folder. Returns number of files deleted."""
        prefix = f"batches/{batch_id}/"
        paginator = self.client.get_paginator("list_objects_v2")
        count = 0
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            objects = page.get("Contents", [])
            if objects:
                delete_keys = [{"Key": obj["Key"]} for obj in objects]
                self.client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={"Objects": delete_keys}
                )
                count += len(objects)
        return count

    async def list_files(self, prefix: str) -> list[str]:
        """List all files with a given prefix. Returns S3 keys."""
        paginator = self.client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys
