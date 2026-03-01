"""
S3 Upload Utility

Handles uploading crawl results to S3-compatible object storage.
Compresses files with gzip before upload to save bandwidth and storage.

boto3 is an optional dependency - install with: pip install boto3
"""

import os
import gzip
import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def is_s3_configured() -> bool:
    """Check if S3 credentials are configured in environment."""
    return all(
        [
            os.getenv("S3_ACCESS_KEY"),
            os.getenv("S3_SECRET_KEY"),
            os.getenv("S3_ENDPOINT"),
            os.getenv("S3_BUCKET"),
        ]
    )


def upload_to_s3(
    file_path: str,
    s3_key: Optional[str] = None,
    compress: bool = True,
    delete_after_upload: bool = False,
) -> bool:
    """
    Upload a file to S3-compatible storage.

    Args:
        file_path: Path to the file to upload
        s3_key: S3 key (path in bucket). If None, uses relative path from data dir
        compress: Whether to gzip compress before upload (default: True)
        delete_after_upload: Whether to delete local file after successful upload

    Returns:
        True if upload succeeded, False otherwise

    Raises:
        ImportError: If boto3 is not installed
        ValueError: If S3 credentials not configured
    """
    # Import boto3
    try:
        import boto3
    except ImportError:
        logger.error("boto3 not installed. Run: pip install -r requirements.txt")
        raise ImportError("boto3 required for S3 uploads")

    # Check S3 configuration
    if not is_s3_configured():
        raise ValueError(
            "S3 credentials not configured. Set S3_ACCESS_KEY, S3_SECRET_KEY, S3_ENDPOINT, and S3_BUCKET in .env"
        )

    # Get S3 credentials
    s3_access_key = os.getenv("S3_ACCESS_KEY")
    s3_secret_key = os.getenv("S3_SECRET_KEY")
    s3_endpoint = os.getenv("S3_ENDPOINT")
    s3_bucket = os.getenv("S3_BUCKET")

    file_path = Path(file_path)

    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return False

    # Determine S3 key (path in bucket)
    if s3_key is None:
        # Use relative path from current directory
        s3_key = file_path.name

    original_size_mb = file_path.stat().st_size / (1024 * 1024)
    logger.info(f"📄 Original file: {file_path.name} ({original_size_mb:.2f} MB)")

    # Compress if requested
    upload_path = file_path
    if compress and not file_path.name.endswith(".gz"):
        gz_path = Path(str(file_path) + ".gz")
        logger.info("🗜️  Compressing to gzip...")

        try:
            with open(file_path, "rb") as f_in:
                with gzip.open(gz_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)

            compressed_size_mb = gz_path.stat().st_size / (1024 * 1024)
            compression_ratio = (1 - compressed_size_mb / original_size_mb) * 100
            logger.info(
                f"✅ Compressed: {compressed_size_mb:.2f} MB (saved {compression_ratio:.1f}%)"
            )

            upload_path = gz_path
            s3_key = s3_key + ".gz"

        except Exception as e:
            logger.error(f"Compression failed: {e}")
            return False

    logger.info(f"📤 Uploading to s3://{s3_bucket}/{s3_key}...")

    try:
        # Initialize S3 client
        s3_client = boto3.client(
            "s3",
            endpoint_url=s3_endpoint,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
        )

        # Upload file
        s3_client.upload_file(str(upload_path), s3_bucket, s3_key)

        logger.info(f"✅ Uploaded to s3://{s3_bucket}/{s3_key}")

        # Clean up compressed file if we created it
        if compress and upload_path != file_path:
            upload_path.unlink()
            logger.debug(f"Cleaned up compressed file: {upload_path.name}")

        # Optionally delete original file
        if delete_after_upload and file_path.exists():
            file_path.unlink()
            logger.info(f"🧹 Deleted local file: {file_path.name}")

        return True

    except Exception as e:
        logger.error(f"❌ Upload failed: {e}")

        # Clean up compressed file if upload failed
        if compress and upload_path != file_path and upload_path.exists():
            upload_path.unlink()

        return False
