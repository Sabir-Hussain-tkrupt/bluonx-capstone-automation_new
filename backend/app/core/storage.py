"""Supabase Storage helper functions.

Thin wrappers around the Supabase storage API for upload, delete,
and signed-URL generation. Used by document upload endpoints.
"""

import logging
from uuid import uuid4

from fastapi import HTTPException, status
from storage3.exceptions import StorageApiError
from supabase import Client

logger = logging.getLogger(__name__)

# Storage-API statuses that mean "this file was rejected", not "storage broke".
# The Supabase storage API answers a bucket-level rejection with a 4xx and a
# usable message ("mime type X is not supported"); collapsing that into a 500
# threw the reason away and made a caller error look like an outage. Any other
# 4xx degrades to 400. 5xx, and anything that is not a StorageApiError at all
# (network, auth, quota), stay 500 with generic copy and a logged cause.
_STORAGE_REJECTION_STATUSES = {
    400: status.HTTP_400_BAD_REQUEST,
    409: status.HTTP_409_CONFLICT,
    413: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    415: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
}


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

    Raises HTTPException(415/413/409/400) when the storage API *rejects* the
    file, carrying its reason through to the caller, and HTTPException(500) for
    every other failure.
    """
    try:
        db.storage.from_(bucket).upload(
            path,
            file_bytes,
            {"content-type": content_type},
        )
        return path
    except StorageApiError as exc:
        # .status comes off the wire as a str ('415'), so coerce defensively:
        # an unparseable value falls through to the 500 branch.
        try:
            api_status = int(exc.status)
        except (TypeError, ValueError):
            api_status = 0
        if 400 <= api_status < 500:
            http_status = _STORAGE_REJECTION_STATUSES.get(
                api_status, status.HTTP_400_BAD_REQUEST
            )
            reason = (getattr(exc, "message", None) or str(exc)).strip()
            logger.warning(
                "Storage rejected upload for %s/%s (%s %s): %s",
                bucket,
                path,
                api_status,
                getattr(exc, "code", None),
                reason,
            )
            raise HTTPException(
                status_code=http_status,
                detail=f"Storage rejected the file: {reason}",
            ) from exc
        logger.error("Storage upload failed for %s/%s: %s", bucket, path, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file to storage.",
        ) from exc
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
