"""
Google Cloud Storage service.
"""
import uuid
from typing import Optional, BinaryIO
from pathlib import Path

from google.cloud import storage
from google.oauth2 import service_account

from app.config import get_settings

settings = get_settings()


class StorageService:
    """Service for Google Cloud Storage operations."""

    def __init__(self):
        """Initialize Storage client."""
        if settings.google_application_credentials:
            credentials = service_account.Credentials.from_service_account_file(
                settings.google_application_credentials
            )
            self.client = storage.Client(
                project=settings.gcp_project_id,
                credentials=credentials
            )
        else:
            # Use default credentials
            self.client = storage.Client(project=settings.gcp_project_id)

        self.bucket_name = settings.gcp_storage_bucket
        self.bucket = self.client.bucket(self.bucket_name)

    def _get_gs_path(self, blob_name: str) -> str:
        """Get the gs:// path for a blob."""
        return f"gs://{self.bucket_name}/{blob_name}"

    async def upload_form(
        self,
        file: BinaryIO,
        filename: str,
        content_type: str = "image/png"
    ) -> str:
        """
        Upload a form template to storage.
        Returns the storage path (gs://bucket/path).
        """
        # Generate unique path
        form_id = str(uuid.uuid4())
        extension = Path(filename).suffix or ".png"
        blob_name = f"forms/{form_id}{extension}"

        blob = self.bucket.blob(blob_name)
        blob.upload_from_file(file, content_type=content_type)

        return self._get_gs_path(blob_name)

    async def upload_synthetic_document(
        self,
        file: BinaryIO,
        batch_id: str,
        document_id: str,
        content_type: str = "image/png"
    ) -> str:
        """
        Upload a synthetic document to storage.
        Returns the storage path.
        """
        blob_name = f"batches/{batch_id}/{document_id}.png"

        blob = self.bucket.blob(blob_name)
        blob.upload_from_file(file, content_type=content_type)

        return self._get_gs_path(blob_name)

    async def upload_bytes(
        self,
        data: bytes,
        blob_name: str,
        content_type: str = "image/png"
    ) -> str:
        """
        Upload bytes to storage.
        Returns the storage path.
        """
        blob = self.bucket.blob(blob_name)
        blob.upload_from_string(data, content_type=content_type)

        return self._get_gs_path(blob_name)

    async def download_file(self, storage_path: str) -> bytes:
        """
        Download a file from storage.
        Accepts either gs://bucket/path or just the path.
        """
        # Extract blob name from gs:// path
        if storage_path.startswith("gs://"):
            # Remove gs://bucket/ prefix
            blob_name = storage_path.replace(f"gs://{self.bucket_name}/", "")
        else:
            blob_name = storage_path

        blob = self.bucket.blob(blob_name)
        return blob.download_as_bytes()

    async def get_signed_url(
        self,
        storage_path: str,
        expiration_minutes: int = 60
    ) -> str:
        """
        Generate a signed URL for temporary access to a file.
        Uses IAM signBlob API when running on Cloud Run (no private key).
        """
        from datetime import timedelta
        import google.auth
        from google.auth.transport import requests as auth_requests

        # Extract blob name from gs:// path
        if storage_path.startswith("gs://"):
            blob_name = storage_path.replace(f"gs://{self.bucket_name}/", "")
        else:
            blob_name = storage_path

        blob = self.bucket.blob(blob_name)

        try:
            # Try direct signing (works with service account key file)
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=expiration_minutes),
                method="GET",
            )
        except AttributeError:
            # On Cloud Run, compute engine credentials don't have a private key.
            # Use the IAM signBlob API instead.
            credentials, project = google.auth.default()
            # Refresh to ensure we have a valid access token
            credentials.refresh(auth_requests.Request())

            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(minutes=expiration_minutes),
                method="GET",
                service_account_email=credentials.service_account_email,
                access_token=credentials.token,
            )

        return url

    async def copy_file(self, source_path: str, dest_blob_name: str) -> str:
        """
        Copy a file within the same bucket (server-side, no download).
        Returns the gs:// path of the new file.
        """
        if source_path.startswith("gs://"):
            source_blob_name = source_path.replace(f"gs://{self.bucket_name}/", "")
        else:
            source_blob_name = source_path

        source_blob = self.bucket.blob(source_blob_name)
        self.bucket.copy_blob(source_blob, self.bucket, dest_blob_name)
        return self._get_gs_path(dest_blob_name)

    async def delete_file(self, storage_path: str) -> bool:
        """
        Delete a file from storage.
        """
        try:
            if storage_path.startswith("gs://"):
                blob_name = storage_path.replace(f"gs://{self.bucket_name}/", "")
            else:
                blob_name = storage_path

            blob = self.bucket.blob(blob_name)
            blob.delete()
            return True
        except Exception:
            return False

    async def delete_batch_folder(self, batch_id: str) -> int:
        """
        Delete all files in a batch folder.
        Returns number of files deleted.
        """
        prefix = f"batches/{batch_id}/"
        blobs = self.bucket.list_blobs(prefix=prefix)

        count = 0
        for blob in blobs:
            blob.delete()
            count += 1

        return count

    async def list_files(self, prefix: str) -> list[str]:
        """
        List all files with a given prefix.
        """
        blobs = self.bucket.list_blobs(prefix=prefix)
        return [self._get_gs_path(blob.name) for blob in blobs]
