"""Tests for expire_revision_requests — the revision-expiry job body."""

from datetime import datetime, timedelta, timezone

from app.jobs.revision_expiry import expire_revision_requests

_NOW = datetime.now(timezone.utc)
PAST = (_NOW - timedelta(hours=1)).isoformat()
FUTURE = (_NOW + timedelta(hours=1)).isoformat()


async def test_pending_past_deadline_is_expired(make_fake_db):
    """Pending + past deadline → expired, responded_at set, token revoked, count=1."""
    db = make_fake_db(
        revision_rows=[
            {
                "id": "r1",
                "bid_invitation_id": "inv1",
                "status": "pending",
                "revision_deadline": PAST,
            }
        ]
    )

    count = await expire_revision_requests(db)

    assert count == 1

    assert len(db.revision_updates) == 1
    rid, payload = db.revision_updates[0]
    assert rid == "r1"
    assert payload["status"] == "expired"
    assert payload["responded_at"] is not None

    assert len(db.token_revocations) == 1
    tok_rid, tok_payload = db.token_revocations[0]
    assert tok_rid == "r1"
    assert tok_payload["revoked_at"] is not None
    assert tok_payload["is_used"] is True
    # No user took this action — revoked_by must not be set.
    assert "revoked_by" not in tok_payload


async def test_pending_future_deadline_unchanged(make_fake_db):
    """Pending + future deadline → not selected by the SELECT filter, count=0."""
    db = make_fake_db(
        revision_rows=[
            {
                "id": "r1",
                "bid_invitation_id": "inv1",
                "status": "pending",
                "revision_deadline": FUTURE,
            }
        ]
    )

    count = await expire_revision_requests(db)

    assert count == 0
    assert db.revision_updates == []
    assert db.token_revocations == []


async def test_already_declined_unchanged(make_fake_db):
    """Declined + past deadline → won't match status='pending' SELECT, count=0."""
    db = make_fake_db(
        revision_rows=[
            {
                "id": "r1",
                "bid_invitation_id": "inv1",
                "status": "declined",
                "revision_deadline": PAST,
            }
        ]
    )

    count = await expire_revision_requests(db)

    assert count == 0
    assert db.revision_updates == []
    assert db.token_revocations == []


async def test_toctou_lost_race_skips_row(make_fake_db):
    """Guarded UPDATE returns empty data (row left pending) → no revocation, count=0."""
    db = make_fake_db(
        revision_rows=[
            {
                "id": "r1",
                "bid_invitation_id": "inv1",
                "status": "pending",
                "revision_deadline": PAST,
            }
        ],
        update_results={"r1": []},  # simulate vendor/PM winning the race
    )

    count = await expire_revision_requests(db)

    assert count == 0
    assert len(db.revision_updates) == 1  # the UPDATE was attempted
    assert db.token_revocations == []  # but no token revocation followed


async def test_multiple_expired(make_fake_db):
    """Several expired requests → all updated, token revocations match the count."""
    db = make_fake_db(
        revision_rows=[
            {
                "id": rid,
                "bid_invitation_id": f"inv-{rid}",
                "status": "pending",
                "revision_deadline": PAST,
            }
            for rid in ("r1", "r2", "r3")
        ]
    )

    count = await expire_revision_requests(db)

    assert count == 3
    assert len(db.token_revocations) == 3
    assert {rid for rid, _ in db.token_revocations} == {"r1", "r2", "r3"}
