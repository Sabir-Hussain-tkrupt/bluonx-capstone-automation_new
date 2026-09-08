"""Unit tests for the extension-first upload validator.

The document router tests patch `validate_upload` out, so this is where the
validation logic is actually exercised: the expanded per-bucket allow-lists,
the loosened MIME handling (generic/octet-stream trusted so CAD/Office get
through), and magic-byte sniffing keyed by extension.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.core.file_validation import BUCKET_CONFIGS, validate_upload

# Office Open XML content types (hardcoded here to keep the test independent of
# the module's internal constants).
_OOXML_MIME_WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_OOXML_MIME_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Byte fixtures (>= 8 bytes so the magic check runs)
PDF = b"%PDF-1.4\n1 0 obj\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
ZIP = b"PK\x03\x04" + b"\x00" * 16          # OOXML .docx / .xlsx
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 8  # legacy .doc / .xls
DWG = b"AC1027\x00\x00" + b"\x00" * 8
TXT = b"just some plain text content"
DXF = b"  0\r\nSECTION\r\n  2\r\nHEADER\r\n"


def _validate(bucket, filename, content_type, data):
    """Raises HTTPException(422) on failure; returns None on success."""
    validate_upload(data, filename, content_type, bucket)


def _assert_rejected(bucket, filename, content_type, data):
    with pytest.raises(HTTPException) as exc:
        _validate(bucket, filename, content_type, data)
    assert exc.value.status_code == 422
    return exc.value


class TestProjectDocuments:
    BUCKET = "project-documents"

    def test_pdf(self):
        _validate(self.BUCKET, "plans.pdf", "application/pdf", PDF)

    def test_docx_with_ooxml_type(self):
        _validate(self.BUCKET, "spec.docx", _OOXML_MIME_WORD, ZIP)

    def test_docx_as_octet_stream_is_trusted(self):
        _validate(self.BUCKET, "spec.docx", "application/octet-stream", ZIP)

    def test_xlsx(self):
        _validate(self.BUCKET, "budget.xlsx", _OOXML_MIME_EXCEL, ZIP)

    def test_legacy_doc_ole(self):
        _validate(self.BUCKET, "old.doc", "application/msword", OLE)

    def test_txt(self):
        _validate(self.BUCKET, "notes.txt", "text/plain", TXT)

    def test_dwg_as_octet_stream(self):
        # CAD arrives as octet-stream; extension + AC10 magic carry it.
        _validate(self.BUCKET, "site.dwg", "application/octet-stream", DWG)

    def test_dxf_as_octet_stream_no_signature(self):
        _validate(self.BUCKET, "site.dxf", "application/octet-stream", DXF)

    def test_rejects_disallowed_extension(self):
        _assert_rejected(self.BUCKET, "malware.exe", "application/octet-stream", PDF)

    def test_rejects_spoof_png_named_pdf(self):
        # Extension + declared type say PDF, but the bytes are a PNG.
        _assert_rejected(self.BUCKET, "fake.pdf", "application/pdf", PNG)

    def test_rejects_specific_contradicting_content_type(self):
        # A *specific* type that contradicts the extension is still rejected.
        _assert_rejected(self.BUCKET, "img.png", "image/jpeg", PNG)


class TestVendorDocuments:
    BUCKET = "vendor-documents"

    def test_pdf(self):
        _validate(self.BUCKET, "w9.pdf", "application/pdf", PDF)

    def test_png(self):
        _validate(self.BUCKET, "scan.png", "image/png", PNG)

    def test_docx(self):
        _validate(self.BUCKET, "mta.docx", _OOXML_MIME_WORD, ZIP)

    def test_rejects_dwg(self):
        _assert_rejected(self.BUCKET, "site.dwg", "application/octet-stream", DWG)

    def test_rejects_xlsx(self):
        _assert_rejected(self.BUCKET, "budget.xlsx", _OOXML_MIME_EXCEL, ZIP)

    def test_rejects_txt(self):
        _assert_rejected(self.BUCKET, "notes.txt", "text/plain", TXT)


class TestBucketConfigShape:
    """Guards the two things that let bucket config drift out of step before.

    `allowed_mimes` was a parallel MIME allow-list nothing read. Its
    project-documents value listed zero CAD types against four CAD extensions,
    so copying it into a Supabase bucket reproduced the exact bug it was
    supposed to document. It is gone; these keep it gone.
    """

    def test_no_bucket_carries_a_mime_allow_list(self):
        for bucket, config in BUCKET_CONFIGS.items():
            assert "allowed_mimes" not in config, (
                f"{bucket} reintroduced allowed_mimes. Extensions are the single "
                "gate (see the module docstring and storage_rls_policies.sql)."
            )

    def test_allowed_mimes_is_referenced_nowhere_in_app(self):
        app_dir = Path(__file__).resolve().parents[1] / "app"
        offenders = [
            str(path.relative_to(app_dir))
            for path in app_dir.rglob("*.py")
            if "allowed_mimes" in path.read_text(encoding="utf-8")
        ]
        assert offenders == [], f"allowed_mimes came back in: {offenders}"

    def test_every_bucket_has_extensions_and_a_size(self):
        for bucket, config in BUCKET_CONFIGS.items():
            assert config["allowed_extensions"], bucket
            assert config["max_size_bytes"] > 0, bucket

    def test_bid_attachment_size_matches_the_router(self):
        """The router enforces 10 MB and rejects first; the config is the backstop.

        Stated in two files, so assert they agree rather than trusting a comment.
        """
        from app.routers.vendor_portal import MAX_ATTACHMENT_BYTES

        assert (
            BUCKET_CONFIGS["bid-attachments"]["max_size_bytes"] == MAX_ATTACHMENT_BYTES
        )

    def test_oversize_bid_attachment_rejected_at_the_config_limit(self):
        limit = BUCKET_CONFIGS["bid-attachments"]["max_size_bytes"]
        oversize = PDF + b"0" * limit
        with pytest.raises(HTTPException) as raised:
            _validate("bid-attachments", "big.pdf", "application/pdf", oversize)
        assert raised.value.status_code == 422
        assert "10MB" in raised.value.detail
