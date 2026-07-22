"""Supabase Storage helper functions.

Thin wrappers around the Supabase storage API for upload, delete,
and signed-URL generation. Used by document upload endpoints.
"""

import logging
from uuid import uuid4

from fastapi import HTTPException, status
from supabase import Client

logger = logging.getLogger(__name__)


def unique_object_path(prefix: str, filename: str) -> str:
    """Build a collision-proof storage key: ``{prefix}/{uuid}/{filename}``.

    The Supabase upload is not upsert-enabled, so a deterministic key made a
    same-named re-upload collide and surface as a 500. A per-upload uuid segment
    keeps the human-readable filename intact (it stays in file_name for display)
    while guaranteeing the object key is unique.
    """
    return f"{prefix}/{uuid4().hex}/{filename}"


def upload_file(
    db: Client,
    bucket: str,
    path: str,
    file_bytes: bytes,
    content_type: str,
) -> str:
    """Upload a file to Supabase Storage.

    Returns the storage path on success.
    Raises HTTPException(500) on failure.
    """
    try:
        db.storage.from_(bucket).upload(
            path,
            file_bytes,
            {"content-type": content_type},
        )
        return path
    except Exception as exc:
        logger.error("Storage upload failed for %s/%s: %s", bucket, path, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file to storage.",
        ) from exc


def delete_file(db: Client, bucket: str, path: str) -> None:
    """Delete a file from Supabase Storage.

    Logs a warning but does not raise if the file is already gone.
    """
    try:
        db.storage.from_(bucket).remove([path])
    except Exception as exc:
        logger.warning("Storage delete failed for %s/%s: %s", bucket, path, exc)


def get_signed_url(
    db: Client,
    bucket: str,
    path: str,
    expires_in: int = 3600,
) -> str:
    """Generate a signed download URL for a storage file.

    Args:
        expires_in: URL validity in seconds (default 1 hour).

    Returns the signed URL string.
    Raises HTTPException(500) on failure.
    """
    try:
        result = db.storage.from_(bucket).create_signed_url(path, expires_in)
        if isinstance(result, dict) and "signedURL" in result:
            return result["signedURL"]
        # supabase-py v2 returns an object with .signed_url
        if hasattr(result, "signed_url"):
            return result.signed_url
        # Fallback: try dict access with snake_case key
        if isinstance(result, dict) and "signed_url" in result:
            return result["signed_url"]
        raise ValueError(f"Unexpected signed URL response format: {result}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Signed URL generation failed for %s/%s: %s", bucket, path, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate download URL.",
        ) from exc
