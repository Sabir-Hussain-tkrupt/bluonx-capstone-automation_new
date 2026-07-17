"""Vendor performance review write-path tests.

Asserts: vendor_id is resolved server-side from the contract (never the client),
one-per-contract (23505 → 409), completed-only guard (409), rating bounds (422),
and that an edit advances reviewed_at/reviewed_by.
"""

from __future__ import annotations

from postgrest.exceptions import APIError

from .conftest import (
    CLIENT_VENDOR_ID,
    CONTRACT_ID,
    CONTRACT_VENDOR_ID,
    REVIEW_ID,
    make_contract_row,
    make_review_row,
)


# ── Create: server-resolved vendor_id ────────────────────────────────────


def test_create_resolves_vendor_id_server_side(recording_client_factory):
    """The written vendor_id must come from the contract, not the request body."""
    spec = {
        "contracts": {"select": make_contract_row(status="completed")},
        "vendor_performance_reviews": {"insert": [make_review_row(rating=5)]},
    }
    client, calls = recording_client_factory(spec)

    resp = client.post(
        f"/api/v1/contracts/{CONTRACT_ID}/review",
        # A malicious/incorrect vendor_id in the body must be ignored — the model
        # doesn't even accept it, but we prove the written value is the contract's.
        json={"rating": 5, "notes": "great work"},
    )
    assert resp.status_code == 201

    inserted = calls["vendor_performance_reviews"]["insert"][0]
    assert inserted["vendor_id"] == str(CONTRACT_VENDOR_ID)
    assert inserted["vendor_id"] != str(CLIENT_VENDOR_ID)
    assert inserted["contract_id"] == str(CONTRACT_ID)
    assert inserted["rating"] == 5


# ── Create: guards ───────────────────────────────────────────────────────


def test_create_on_non_completed_contract_is_409(recording_client_factory):
    spec = {"contracts": {"select": make_contract_row(status="executed")}}
    client, _ = recording_client_factory(spec)
    resp = client.post(
        f"/api/v1/contracts/{CONTRACT_ID}/review", json={"rating": 4}
    )
    assert resp.status_code == 409


def test_create_on_missing_contract_is_404(recording_client_factory):
    spec = {"contracts": {"select": None}}
    client, _ = recording_client_factory(spec)
    resp = client.post(
        f"/api/v1/contracts/{CONTRACT_ID}/review", json={"rating": 4}
    )
    assert resp.status_code == 404


def test_second_review_is_409(recording_client_factory):
    dup = APIError({"code": "23505", "message": "duplicate key value"})
    spec = {
        "contracts": {"select": make_contract_row(status="completed")},
        "vendor_performance_reviews": {"insert": dup},
    }
    client, _ = recording_client_factory(spec)
    resp = client.post(
        f"/api/v1/contracts/{CONTRACT_ID}/review", json={"rating": 4}
    )
    assert resp.status_code == 409


def test_rating_out_of_range_is_422(recording_client_factory):
    spec = {"contracts": {"select": make_contract_row(status="completed")}}
    client, _ = recording_client_factory(spec)
    for bad in (0, 6, -1):
        resp = client.post(
            f"/api/v1/contracts/{CONTRACT_ID}/review", json={"rating": bad}
        )
        assert resp.status_code == 422, f"rating={bad} should be rejected"


# ── Update ───────────────────────────────────────────────────────────────


def test_update_advances_reviewed_at_and_by(recording_client_factory):
    spec = {"vendor_performance_reviews": {"update": [make_review_row(rating=2)]}}
    client, calls = recording_client_factory(spec)

    resp = client.patch(f"/api/v1/reviews/{REVIEW_ID}", json={"rating": 2})
    assert resp.status_code == 200

    updated = calls["vendor_performance_reviews"]["update"][0]
    assert updated["rating"] == 2
    assert "reviewed_at" in updated
    assert "reviewed_by" in updated


def test_update_missing_review_is_404(recording_client_factory):
    spec = {"vendor_performance_reviews": {"update": []}}
    client, _ = recording_client_factory(spec)
    resp = client.patch(f"/api/v1/reviews/{REVIEW_ID}", json={"rating": 3})
    assert resp.status_code == 404


def test_update_rating_only_leaves_notes_untouched(recording_client_factory):
    """A rating-only edit must not touch notes (no accidental wipe)."""
    spec = {"vendor_performance_reviews": {"update": [make_review_row(rating=5)]}}
    client, calls = recording_client_factory(spec)

    resp = client.patch(f"/api/v1/reviews/{REVIEW_ID}", json={"rating": 5})
    assert resp.status_code == 200

    updated = calls["vendor_performance_reviews"]["update"][0]
    assert updated["rating"] == 5
    assert "notes" not in updated  # omitted → not written


def test_update_explicit_null_notes_clears_them(recording_client_factory):
    """Sending notes: null explicitly clears the note."""
    spec = {"vendor_performance_reviews": {"update": [make_review_row(rating=5)]}}
    client, calls = recording_client_factory(spec)

    resp = client.patch(
        f"/api/v1/reviews/{REVIEW_ID}", json={"rating": 5, "notes": None}
    )
    assert resp.status_code == 200

    updated = calls["vendor_performance_reviews"]["update"][0]
    assert updated["notes"] is None  # explicit → cleared
