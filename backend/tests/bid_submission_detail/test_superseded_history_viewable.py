"""
Step 3 contract lock — the PM by-id bid detail endpoint MUST remain
history-viewable. A superseded submission fetched directly returns 200
(NOT 404). The version-history expander in the PM comparison view
deep-links to specific superseded submissions via this path; a future
change must not silently filter it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.auth import get_current_active_user
from app.main import app
from app.core.supabase_client import get_supabase

from uuid import uuid4

from .conftest import (
    SUBMISSION_ID,
    build_chain,
    _make_signed_url_storage_mock,
)

URL = f"/api/v1/bid-submissions/{SUBMISSION_ID}"
PREDECESSOR_ID = str(uuid4())


@pytest.fixture()
def superseded_client(sample_submission_row, sample_line_items_unordered,
                       sample_attachments, authed_user):
    sub = dict(sample_submission_row)
    sub["is_superseded"] = True
    sub["supersedes_submission_id"] = PREDECESSOR_ID
    sub["revision_number"] = 2

    client = MagicMock()

    def table_side_effect(name: str):
        if name == "bid_submissions":
            return build_chain(data=sub)
        if name == "bid_line_items":
            return build_chain(data=sample_line_items_unordered)
        if name == "bid_attachments":
            return build_chain(data=sample_attachments)
        return build_chain(data=[])

    client.table.side_effect = table_side_effect
    client.storage = _make_signed_url_storage_mock()

    app.dependency_overrides[get_current_active_user] = lambda: authed_user
    app.dependency_overrides[get_supabase] = lambda: client
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_superseded_submission_detail_still_200(superseded_client):
    resp = superseded_client.get(URL)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(SUBMISSION_ID)
    # Revision metadata so the SPA can render a "Historical version" badge.
    assert body["is_superseded"] is True
    assert body["supersedes_submission_id"] is not None
    assert body["revision_number"] >= 2
