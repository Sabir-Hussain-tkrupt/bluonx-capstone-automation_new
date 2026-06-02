"""
Delete-message upgrade tests for DELETE /bid-templates/{id}.

Acceptance criterion (Task 8.1): the existing FK RESTRICT block stays;
the 409 message now names the referencing package(s) and their status.
This includes cancelled references; FK blocks on *any* reference.
"""

from __future__ import annotations

from .conftest import TEMPLATE_ID


def test_delete_409_lists_open_referencing_package(client_live_open):
    client, db = client_live_open

    resp = client.delete(f"/api/v1/bid-templates/{TEMPLATE_ID}")

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "rough grading" in detail.lower()
    assert "open" in detail.lower()


def test_delete_409_lists_cancelled_referencing_package(client_cancelled_only):
    """FK RESTRICT blocks on cancelled refs too; message must say so."""
    client, db = client_cancelled_only

    resp = client.delete(f"/api/v1/bid-templates/{TEMPLATE_ID}")

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "cancelled scope" in detail.lower()
    assert "cancelled" in detail.lower()


def test_delete_204_when_no_references(client_no_refs):
    client, db = client_no_refs

    resp = client.delete(f"/api/v1/bid-templates/{TEMPLATE_ID}")

    assert resp.status_code == 204, resp.text


def test_delete_409_mentions_all_referencing_packages_in_mixed(client_mixed):
    client, db = client_mixed

    resp = client.delete(f"/api/v1/bid-templates/{TEMPLATE_ID}")

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"].lower()
    assert "rough grading" in detail
    assert "cancelled scope" in detail


def test_delete_409_caps_long_package_list_with_overflow_indicator(client_many_live):
    """Five referencing packages -> message shows 3 by name + '+2 more'.

    Avoids runaway messages when a template is heavily used (the failure
    mode the PM-side caps protect against).
    """
    client, db = client_many_live

    resp = client.delete(f"/api/v1/bid-templates/{TEMPLATE_ID}")

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    # First 3 task names appear; the last 2 collapse into '+2 more'.
    assert "Task 0" in detail
    assert "Task 1" in detail
    assert "Task 2" in detail
    assert "Task 3" not in detail
    assert "Task 4" not in detail
    assert "+2 more" in detail
