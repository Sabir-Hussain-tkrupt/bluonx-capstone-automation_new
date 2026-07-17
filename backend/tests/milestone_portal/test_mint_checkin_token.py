"""
mint_checkin_token primitive (Phase 10.2).

Creates the vendor check-in alert row + its token together and returns the
portal URL. Driven by FakeDB; no real DB or send job involved.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.core.config import settings
from app.services.milestone_service import MilestoneError
from app.services.milestone_token_service import TOKEN_TTL_DAYS, mint_checkin_token

MS_ID = str(uuid4())
VENDOR_ID = str(uuid4())
CONTACT_ID = str(uuid4())


def _tables(*, primary=True):
    return {
        "milestones": [{"id": MS_ID, "contracts": {"vendor_id": VENDOR_ID}}],
        "vendor_contacts": (
            [{"id": CONTACT_ID, "vendor_id": VENDOR_ID, "is_primary": True}]
            if primary
            else []
        ),
        "milestone_alerts": [],
        "milestone_checkin_tokens": [],
    }


def test_mint_creates_alert_and_token_and_returns_url(make_db):
    db = make_db(_tables())
    raw_token, portal_url = mint_checkin_token(
        db, milestone_id=MS_ID, alert_type="progress_check", cycle_number=2
    )

    assert portal_url == f"{settings.PORTAL_BASE_URL}/milestone/{raw_token}"

    # One vendor alert row for this milestone + cycle.
    alert_inserts = [rows for t, rows in db.inserts if t == "milestone_alerts"]
    assert len(alert_inserts) == 1
    alert = alert_inserts[0][0]
    assert alert["recipient_type"] == "vendor"
    assert alert["alert_type"] == "progress_check"
    assert alert["cycle_number"] == 2

    # One token row wired to that alert, with the primary contact + 7d expiry.
    token_inserts = [rows for t, rows in db.inserts if t == "milestone_checkin_tokens"]
    assert len(token_inserts) == 1
    token = token_inserts[0][0]
    assert token["milestone_alert_id"] == alert["id"]
    assert token["vendor_contact_id"] == CONTACT_ID
    assert token["cycle_number"] == 2
    assert token["token_hash"] and token["token_hash"] != raw_token  # hashed, not raw
    assert token["is_used"] is False
    assert "expires_at" in token
    assert TOKEN_TTL_DAYS == 7


def test_rejects_non_vendor_alert_type(make_db):
    db = make_db(_tables())
    with pytest.raises(MilestoneError) as ei:
        mint_checkin_token(db, milestone_id=MS_ID, alert_type="delay_alert", cycle_number=1)
    assert ei.value.status_code == 422
    assert not db.inserts  # nothing written


def test_missing_primary_contact_raises(make_db):
    db = make_db(_tables(primary=False))
    with pytest.raises(MilestoneError) as ei:
        mint_checkin_token(
            db, milestone_id=MS_ID, alert_type="start_check", cycle_number=1
        )
    assert ei.value.status_code == 422
