"""S3 storage service for uploading and downloading documents."""
import io
import logging
from typing import Optional

import boto3
from PIL import Image

from ..config import get_settings

logger = logging.getLogger(__name__)

_s3_client = None


def _get_client():
    global _s3_client
    if _s3_client is None:
        settings = get_settings()
        kwargs = {"region_name": settings.aws_default_region}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            kwargs["aws_access_key_id"] = settings.aws_access_key_id
            kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
        # Otherwise uses default credential chain (IAM role)
        _s3_client = boto3.client("s3", **kwargs)
    return _s3_client


def upload_bytes(key: str, data: bytes, content_type: str = "image/png") -> str:
    """Upload bytes to S3. Returns the S3 key."""
    settings = get_settings()
    client = _get_client()
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    logger.info(f"Uploaded {len(data)} bytes to s3://{settings.s3_bucket}/{key}")
    return key


def upload_image(key: str, image: Image.Image, format: str = "PNG") -> str:
    """Upload a PIL Image to S3."""
    buf = io.BytesIO()
    image.save(buf, format=format)
    ct = "image/png" if format.upper() == "PNG" else "image/jpeg"
    return upload_bytes(key, buf.getvalue(), content_type=ct)


def download_bytes(key: str) -> bytes:
    """Download bytes from S3."""
    settings = get_settings()
    client = _get_client()
    resp = client.get_object(Bucket=settings.s3_bucket, Key=key)
    return resp["Body"].read()


def download_image(key: str) -> Image.Image:
    """Download an image from S3 as a PIL Image."""
    data = download_bytes(key)
    return Image.open(io.BytesIO(data))


def generate_presigned_url(key: str, expiry: int = 3600) -> str:
    """Generate a presigned URL for an S3 object."""
    settings = get_settings()
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expiry,
    )
