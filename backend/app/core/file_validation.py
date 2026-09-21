"""File validation utilities for document uploads.

Validates MIME types, file sizes, extensions, and magic bytes
per bucket configuration defined in docs/task_1.6_storage_bucket_setup.md.
"""

import os
import re

from fastapi import HTTPException, status


# ── Bucket configurations ────────────────# Office (OOXML .docx/.xlsx/.pptx are ZIP; legacy .doc/.xls/.ppt are OLE compound files).
_OOXML_MIME_WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_OOXML_MIME_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_OOXML_MIME_POWERPOINT = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

_COMMON_DOCUMENT_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tif", ".tiff",
    ".txt", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
}

# `allowed_extensions` is the single MIME/type gate for uploads.
BUCKET_CONFIGS: dict[str, dict] = {
    "vendor-documents": {
        "max_size_bytes": 50 * 1024 * 1024,  # 50 MB (dev)
        "allowed_extensions": _COMMON_DOCUMENT_EXTENSIONS,
    },
    "project-documents": {
        "max_size_bytes": 50 * 1024 * 1024,  # 50 MB (dev)
        "allowed_extensions": _COMMON_DOCUMENT_EXTENSIONS | {
            ".dwg", ".dxf", ".dwf", ".dgn",
        },
    },
    "bid-attachments": {
        "max_size_bytes": 10 * 1024 * 1024,  # 10 MB
        "allowed_extensions": _COMMON_DOCUMENT_EXTENSIONS,
    },
}


# ── Content-type handling ────────────────────────────────────────────────

# Browsers send these when they can't (or don't) determine a specific type — CAD
# and, occasionally, Office files arrive this way. Treated as "trust the
# extension" rather than rejected outright.
_GENERIC_CONTENT_TYPES = {"", "application/octet-stream", "application/x-download"}

# Expected MIME(s) per extension, used only to catch an obvious mismatch when a
# *specific* content-type is declared (e.g. a PNG renamed .pdf).
EXTENSION_TO_MIME: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".gif": {"image/gif"},
    ".webp": {"image/webp"},
    ".bmp": {"image/bmp", "image/x-ms-bmp"},
    ".svg": {"image/svg+xml"},
    ".tif": {"image/tiff"},
    ".tiff": {"image/tiff"},
    ".txt": {"text/plain"},
    ".doc": {"application/msword"},
    ".docx": {_OOXML_MIME_WORD},
    ".xls": {"application/vnd.ms-excel"},
    ".xlsx": {_OOXML_MIME_EXCEL},
    ".ppt": {"application/vnd.ms-powerpoint"},
    ".pptx": {_OOXML_MIME_POWERPOINT},
}


# ── Magic byte signatures (keyed by extension) ───────────────────────────

# Keyed by extension, not content-type, so a CAD/Office file that arrives as
# application/octet-stream still gets sniffed. Extensions absent here have no
# reliable signature (.txt, .svg, .dxf, .dwf, .dgn) and are accepted on extension alone.
_ZIP = [b"PK\x03\x04"]  # OOXML .docx/.xlsx/.pptx are ZIP containers
_OLE = [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"]  # legacy .doc/.xls/.ppt compound files
EXTENSION_SIGNATURES: dict[str, list[bytes]] = {
    ".pdf": [b"%PDF"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png": [b"\x89PNG"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"],
    ".bmp": [b"BM"],
    ".tif": [b"II\x2a\x00", b"MM\x00\x2a"],
    ".tiff": [b"II\x2a\x00", b"MM\x00\x2a"],
    ".docx": _ZIP,
    ".xlsx": _ZIP,
    ".pptx": _ZIP,
    ".doc": _OLE,
    ".xls": _OLE,
    ".ppt": _OLE,
    ".dwg": [b"AC10"],  # AutoCAD version tag, e.g. AC1027/AC1032
}


def _check_magic_bytes(file_bytes: bytes, ext: str) -> bool:
    """Whether file content matches the expected signature for its extension."""
    signatures = EXTENSION_SIGNATURES.get(ext)
    if signatures is None:
        # No reliable signature for this extension — skip the check.
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

    # 2. Extension is the primary gate. CAD/Office files often arrive as
    #    application/octet-stream, so the declared MIME can't be the gate.
    ext = os.path.splitext(filename)[1].lower()
    if ext not in config["allowed_extensions"]:
        allowed_ext = ", ".join(sorted(config["allowed_extensions"]))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File extension '{ext}' is not allowed. Accepted extensions: {allowed_ext}",
        )

    # 3. Content-type is advisory. A generic/blank type is trusted (extension is
    #    already vetted); a *specific* declared type that contradicts the
    #    extension is rejected, which still catches an image renamed .pdf.
    normalized_ct = (content_type or "").lower()
    expected_mimes = EXTENSION_TO_MIME.get(ext)
    if (
        normalized_ct not in _GENERIC_CONTENT_TYPES
        and expected_mimes
        and normalized_ct not in expected_mimes
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File extension '{ext}' does not match content type '{content_type}'.",
        )

    # 4. Magic byte validation, keyed by extension (so octet-stream CAD/Office is
    #    still sniffed where a signature exists; unsignatured types are skipped).
    if len(file_bytes) >= 8 and not _check_magic_bytes(file_bytes, ext):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File content does not match its declared type. The file may be corrupted or mislabeled.",
        )
