"""PATCH /contract-signers/{id} — the last-signer guard and patch fidelity."""

from uuid import uuid4

from .conftest import signer_row


def test_deactivating_the_last_active_signer_is_409(admin_client):
    """Awards cannot be created with no active signer, so the roster must never
    be emptied. Mirrors the last-admin guard in user_service."""
    only = signer_row(is_active=True)
    tc = admin_client({"signers": [only]})

    resp = tc.patch(f"/api/v1/contract-signers/{only['id']}", json={"is_active": False})

    assert resp.status_code == 409
    assert "last active" in resp.json()["detail"].lower()
    # The row is untouched.
    assert tc.db.rows[0]["is_active"] is True


def test_inactive_rows_do_not_count_toward_the_guard(admin_client):
    """One active + several inactive is still "the last one"."""
    only = signer_row(is_active=True, email="active@bluonx.dev")
    tc = admin_client(
        {
            "signers": [
                only,
                signer_row(is_active=False, email="a@bluonx.dev"),
                signer_row(is_active=False, email="b@bluonx.dev"),
            ]
        }
    )

    resp = tc.patch(f"/api/v1/contract-signers/{only['id']}", json={"is_active": False})
    assert resp.status_code == 409


def test_deactivating_succeeds_when_others_remain_active(admin_client):
    target = signer_row(is_active=True, email="one@bluonx.dev")
    tc = admin_client(
        {"signers": [target, signer_row(is_active=True, email="two@bluonx.dev")]}
    )

    resp = tc.patch(f"/api/v1/contract-signers/{target['id']}", json={"is_active": False})

    assert resp.status_code == 200
    assert resp.json()["is_active"] is False
    assert tc.db.rows[0]["is_active"] is False


def test_reactivating_is_never_guarded(admin_client):
    """The guard only fires on deactivation. Turning one back on is always fine,
    even when it is currently the only row."""
    target = signer_row(is_active=False)
    tc = admin_client({"signers": [target]})

    resp = tc.patch(f"/api/v1/contract-signers/{target['id']}", json={"is_active": True})

    assert resp.status_code == 200
    assert resp.json()["is_active"] is True


def test_patching_title_alone_actually_writes(admin_client):
    """model_dump(exclude_unset=True) silently drops any field the update model
    does not declare, returning 200 having written nothing. Every writable field
    must be declared on ContractSignerUpdate."""
    target = signer_row(title="VP of Development")
    tc = admin_client({"signers": [target]})

    resp = tc.patch(
        f"/api/v1/contract-signers/{target['id']}", json={"title": "Chief Operating Officer"}
    )

    assert resp.status_code == 200
    assert resp.json()["title"] == "Chief Operating Officer"
    assert tc.db.rows[0]["title"] == "Chief Operating Officer"


def test_patching_full_name_and_email_normalizes(admin_client):
    target = signer_row()
    tc = admin_client({"signers": [target, signer_row(email="other@bluonx.dev")]})

    resp = tc.patch(
        f"/api/v1/contract-signers/{target['id']}",
        json={"full_name": "  Dana R. Reyes  ", "email": "  Dana.R@BluOnX.dev  "},
    )

    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Dana R. Reyes"
    assert resp.json()["email"] == "dana.r@bluonx.dev"


def test_patch_unknown_signer_is_404(admin_client):
    tc = admin_client({"signers": [signer_row()]})
    resp = tc.patch(f"/api/v1/contract-signers/{uuid4()}", json={"title": "X"})
    assert resp.status_code == 404


def test_no_delete_endpoint(admin_client):
    """Revocation is is_active=false; awards.signer_id is ON DELETE RESTRICT."""
    target = signer_row()
    tc = admin_client({"signers": [target]})
    resp = tc.delete(f"/api/v1/contract-signers/{target['id']}")
    assert resp.status_code == 405
