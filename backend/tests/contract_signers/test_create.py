"""POST /contract-signers — normalization and the two distinct duplicate paths."""

from .conftest import signer_row, unique_violation

NEW = {"full_name": "  Priya Raman  ", "email": "  Priya.Raman@BluOnX.dev  ", "title": "Director"}


def test_create_trims_and_lowercases_email(admin_client):
    tc = admin_client({"signers": []})
    resp = tc.post("/api/v1/contract-signers", json=NEW)

    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "priya.raman@bluonx.dev"
    assert body["full_name"] == "Priya Raman"
    # The normalized values are what actually landed in the table, not just what
    # the response echoed.
    stored = tc.db.rows[0]
    assert stored["email"] == "priya.raman@bluonx.dev"
    assert stored["full_name"] == "Priya Raman"


def test_create_optional_title_may_be_omitted(admin_client):
    tc = admin_client({"signers": []})
    resp = tc.post(
        "/api/v1/contract-signers",
        json={"full_name": "Sam Okoro", "email": "sam@bluonx.dev"},
    )
    assert resp.status_code == 201
    assert resp.json()["title"] is None


def test_duplicate_active_email_is_409_not_500(admin_client):
    tc = admin_client({"signers": [signer_row(email="dana@bluonx.dev", is_active=True)]})
    resp = tc.post(
        "/api/v1/contract-signers",
        # Different case — the normalized comparison must still catch it.
        json={"full_name": "Dana R", "email": "DANA@bluonx.dev"},
    )

    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"].lower()
    # Nothing was written.
    assert len(tc.db.rows) == 1


def test_duplicate_inactive_email_directs_to_reactivation(admin_client):
    """An inactive row with the same email is a different situation from a live
    duplicate: the admin should be told to reactivate, not that the name is taken."""
    tc = admin_client({"signers": [signer_row(email="dana@bluonx.dev", is_active=False)]})
    resp = tc.post(
        "/api/v1/contract-signers",
        json={"full_name": "Dana Reyes", "email": "dana@bluonx.dev"},
    )

    assert resp.status_code == 409
    detail = resp.json()["detail"].lower()
    assert "deactivated" in detail
    assert "reactivate" in detail
    assert len(tc.db.rows) == 1


def test_the_two_duplicate_messages_are_distinct(admin_client):
    """Guards against collapsing both branches onto one string."""
    body = {"full_name": "Dana Reyes", "email": "dana@bluonx.dev"}

    active_tc = admin_client({"signers": [signer_row(email="dana@bluonx.dev", is_active=True)]})
    active_detail = active_tc.post("/api/v1/contract-signers", json=body).json()["detail"]

    inactive_tc = admin_client({"signers": [signer_row(email="dana@bluonx.dev", is_active=False)]})
    inactive_detail = inactive_tc.post("/api/v1/contract-signers", json=body).json()["detail"]

    assert active_detail != inactive_detail


def test_postgres_23505_surfaces_as_409_not_500(admin_client):
    """Backstop for the race where the pre-check passes but the insert collides."""
    tc = admin_client(
        {"signers": [], "raise_on": {"contract_signers": {"insert": unique_violation()}}}
    )
    resp = tc.post(
        "/api/v1/contract-signers",
        json={"full_name": "Dana Reyes", "email": "dana@bluonx.dev"},
    )

    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"].lower()


def test_malformed_email_is_rejected(admin_client):
    tc = admin_client({"signers": []})
    resp = tc.post(
        "/api/v1/contract-signers", json={"full_name": "Dana", "email": "not-an-email"}
    )
    assert resp.status_code == 422
