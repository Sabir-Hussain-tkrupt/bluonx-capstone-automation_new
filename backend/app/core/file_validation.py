"""File validation utilities for document uploads.

Validates MIME types, file sizes, extensions, and magic bytes
per bucket configuration defined in docs/task_1.6_storage_bucket_setup.md.
"""

import os
import re

from fastapi import HTTPException, status


# ── Bucket configurations ────────────────────────────────────────────────

BUCKET_CONFIGS: dict[str, dict] = {
    "vendor-documents": {
        "max_size_bytes": 50 * 1024 * 1024,  # 50 MB (dev)
        "allowed_mimes": {
            "application/pdf",
            "image/jpeg",
            "image/png",
        },
        "allowed_extensions": {".pdf", ".jpg", ".jpeg", ".png"},
    },
    "project-documents": {
        "max_size_bytes": 50 * 1024 * 1024,  # 50 MB (dev)
        "allowed_mimes": {
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/tiff",
        },
        "allowed_extensions": {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff"},
    },
    "bid-attachments": {
        "max_size_bytes": 50 * 1024 * 1024,  # 50 MB (dev)
        "allowed_mimes": {
            "application/pdf",
            "image/jpeg",
            "image/png",
        },
        "allowed_extensions": {".pdf", ".jpg", ".jpeg", ".png"},
    },
}


# ── Magic byte signatures ────────────────────────────────────────────────

MAGIC_BYTES: dict[str, list[bytes]] = {
    "application/pdf": [b"%PDF"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG"],
    "image/tiff": [b"II\x2a\x00", b"MM\x00\x2a"],  # little-endian / big-endian
}

# Map extensions to expected MIME types
EXTENSION_TO_MIME: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".tif": {"image/tiff"},
    ".tiff": {"image/tiff"},
}


def _check_magic_bytes(file_bytes: bytes, content_type: str) -> bool:
    """Check if file content matches expected magic bytes for the MIME type."""
    signatures = MAGIC_BYTES.get(content_type)
    if signatures is None:
        # No magic bytes defined for this type — skip check
        return True
    return any(file_bytes[: len(sig)] == sig for sig in signatures)


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe storage.

    - Strips path components (prevents path traversal)
    - Limits length to 255 chars
    - Replaces unsafe characters with underscores
    - Preserves the extension
    """
    # Strip path components
    filename = os.path.basename(filename)

    # Split name and extension
    name, ext = os.path.splitext(filename)

    # Replace unsafe chars (keep alphanumeric, hyphens, underscores, dots)
    name = re.sub(r"[^\w\-.]", "_", name)

    # Limit length (leave room for extension)
    max_name_len = 255 - len(ext)
    name = name[:max_name_len]

    # Ensure non-empty name
    if not name:
        name = "document"

    return f"{name}{ext}"


def validate_upload(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    bucket: str,
) -> None:
    """Validate a file upload against bucket rules.

    Raises HTTPException(422) with a descriptive error on failure.
    """
    config = BUCKET_CONFIGS.get(bucket)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown storage bucket: {bucket}",
        )

    # 1. Check file size
    if len(file_bytes) > config["max_size_bytes"]:
        max_mb = config["max_size_bytes"] / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File exceeds the {max_mb:.0f}MB size limit.",
        )

    # 2. Check MIME type
    if content_type not in config["allowed_mimes"]:
        allowed = ", ".join(sorted(config["allowed_mimes"]))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File type '{content_type}' is not allowed. Accepted types: {allowed}",
        )

    # 3. Check extension matches MIME
    ext = os.path.splitext(filename)[1].lower()
    expected_mimes = EXTENSION_TO_MIME.get(ext)
    if expected_mimes and content_type not in expected_mimes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File extension '{ext}' does not match content type '{content_type}'.",
        )

    # 4. Also verify extension is in allowed set
    if ext not in config["allowed_extensions"]:
        allowed_ext = ", ".join(sorted(config["allowed_extensions"]))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File extension '{ext}' is not allowed. Accepted extensions: {allowed_ext}",
        )

    # 5. Magic byte validation
    if len(file_bytes) >= 8 and not _check_magic_bytes(file_bytes, content_type):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File content does not match its declared type. The file may be corrupted or mislabeled.",
        )
