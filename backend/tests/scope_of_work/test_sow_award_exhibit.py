"""Signed Scope of Work — award-time exhibit repoint.

_fetch_sow_exhibits must exhibit the package's PM-uploaded SoW document
(project_documents via bid_packages.scope_of_work_document_id) from the
project-documents bucket, and must NOT exhibit vendor bid_attachments.
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

from app.services.contract_envelope_service import _SOW_BUCKET, _fetch_sow_exhibits


def _db_returning_sow(file_path="proj/sow/scope.pdf", file_name="scope.pdf", raw=b"PDFDATA"):
    """Mock the two explicit lookups: submission chain → SoW id, then the doc."""
    db = MagicMock()
    tables_queried: list[str] = []

    # Submission chain resolves the SoW document id (None → no SoW pinned).
    chain_row = {
        "bid_invitations": {
            "bid_packages": {"scope_of_work_document_id": "doc-1" if file_path else None}
        }
    }
    doc_row = {"file_name": file_name, "file_path": file_path}

    def _table(name):
        tables_queried.append(name)
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.limit.return_value = chain
        if name == "bid_submissions":
            chain.execute.return_value = MagicMock(data=[chain_row])
        elif name == "project_documents":
            chain.execute.return_value = MagicMock(data=[doc_row] if file_path else [])
        else:
            chain.execute.return_value = MagicMock(data=[])
        return chain

    db.table.side_effect = _table

    storage = MagicMock()
    storage.download.return_value = raw
    db.storage.from_.return_value = storage

    return db, tables_queried


def test_exhibits_package_sow_from_project_documents_bucket():
    db, tables_queried = _db_returning_sow()
    exhibits = _fetch_sow_exhibits("sub-1", db=db)

    assert len(exhibits) == 1
    ex = exhibits[0]
    assert ex["name"] == "scope.pdf"
    assert ex["document_id"] == "2"  # contract PDF is document 1
    assert ex["file_extension"] == "pdf"
    assert base64.b64decode(ex["document_base64"]) == b"PDFDATA"

    # Downloads from the project-documents bucket, NOT bid-attachments.
    assert _SOW_BUCKET == "project-documents"
    db.storage.from_.assert_called_once_with("project-documents")
    db.storage.from_.return_value.download.assert_called_once_with("proj/sow/scope.pdf")


def test_does_not_query_vendor_bid_attachments():
    db, tables_queried = _db_returning_sow()
    _fetch_sow_exhibits("sub-1", db=db)
    assert "bid_attachments" not in tables_queried
    assert "bid_submissions" in tables_queried


def test_missing_sow_yields_no_exhibit_and_no_download():
    db, _ = _db_returning_sow(file_path=None)
    exhibits = _fetch_sow_exhibits("sub-1", db=db)
    assert exhibits == []
    db.storage.from_.return_value.download.assert_not_called()
