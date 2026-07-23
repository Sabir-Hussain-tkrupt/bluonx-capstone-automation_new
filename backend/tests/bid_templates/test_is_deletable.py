"""
`is_deletable` on the list and detail responses.

The flag exists because `is_in_use` cannot gate the delete button: it counts
non-cancelled packages only, so a template referenced solely by a cancelled
package reads is_in_use=False and DELETE still fails on the RESTRICT FK. The
cancelled-only case is the whole reason for the second flag, so it gets the
most attention here.
"""

from __future__ import annotations

from uuid import uuid4

from .conftest import (
    TEMPLATE_ID,
    build_simple_chain,
    build_templates_chain,
    build_trades_chain,
    make_db,
    make_template,
)


def _pkg(template_id, status):
    return {"bid_template_id": str(template_id), "status": status}


def _db(templates, packages, active_trade):
    return make_db({
        "bid_templates": build_templates_chain(
            templates, target=templates[0] if templates else None
        ),
        "bid_template_items": build_simple_chain(data=[]),
        "trades": build_trades_chain([active_trade]),
        "bid_packages": build_simple_chain(data=packages),
    })


# ── List ───────────────────────────────────────────────────────────────────


def test_list_marks_unreferenced_template_deletable(client_factory, active_trade):
    t = make_template()
    client = client_factory(_db([t], [], active_trade))
    row = client.get("/api/v1/bid-templates").json()["items"][0]
    assert row["is_deletable"] is True
    assert row["is_in_use"] is False


def test_list_marks_live_referenced_template_not_deletable(client_factory, active_trade):
    t = make_template()
    client = client_factory(_db([t], [_pkg(t["id"], "open")], active_trade))
    row = client.get("/api/v1/bid-templates").json()["items"][0]
    assert row["is_deletable"] is False
    assert row["is_in_use"] is True


def test_list_cancelled_only_is_not_deletable_but_not_in_use(client_factory, active_trade):
    """The case the flag exists for: editable, but permanently undeletable."""
    t = make_template()
    client = client_factory(_db([t], [_pkg(t["id"], "cancelled")], active_trade))
    row = client.get("/api/v1/bid-templates").json()["items"][0]
    assert row["is_in_use"] is False
    assert row["is_deletable"] is False


def test_list_flags_are_per_row(client_factory, active_trade):
    used = make_template(name="Used")
    free = make_template(name="Free", template_id=uuid4())
    client = client_factory(
        _db([used, free], [_pkg(used["id"], "cancelled")], active_trade)
    )
    by_name = {r["name"]: r for r in client.get("/api/v1/bid-templates").json()["items"]}
    assert by_name["Used"]["is_deletable"] is False
    assert by_name["Free"]["is_deletable"] is True


def test_list_still_issues_one_bid_packages_query(client_factory, active_trade):
    """Both flags must come from the same fetch, not two."""
    templates = [make_template(name=f"T{i}", template_id=uuid4()) for i in range(4)]
    db = _db(templates, [], active_trade)
    client = client_factory(db)
    assert client.get("/api/v1/bid-templates").status_code == 200
    assert db._recorder.chain("bid_packages").execute.call_count == 1


# ── Detail ─────────────────────────────────────────────────────────────────


def _detail_pkg(pkg_id, task_name, status):
    return {
        "id": str(pkg_id),
        "status": status,
        "task_id": str(uuid4()),
        "tasks": {"name": task_name},
        "bid_template_id": str(TEMPLATE_ID),
    }


def test_detail_unreferenced_is_deletable(client_factory, active_trade):
    t = make_template()
    client = client_factory(_db([t], [], active_trade))
    body = client.get(f"/api/v1/bid-templates/{TEMPLATE_ID}").json()
    assert body["is_deletable"] is True


def test_detail_cancelled_only_is_not_deletable(client_factory, active_trade):
    t = make_template()
    packages = [_detail_pkg(uuid4(), "Cancelled Scope", "cancelled")]
    client = client_factory(_db([t], packages, active_trade))
    body = client.get(f"/api/v1/bid-templates/{TEMPLATE_ID}").json()

    assert body["is_deletable"] is False
    # Still editable, and the cancelled package is not surfaced as a blocker.
    assert body["is_in_use"] is False
    assert body["referencing_packages"] == []
    assert body["referencing_packages_total"] == 0


def test_detail_live_reference_sets_both_flags(client_factory, active_trade):
    t = make_template()
    packages = [_detail_pkg(uuid4(), "Rough Grading", "open")]
    client = client_factory(_db([t], packages, active_trade))
    body = client.get(f"/api/v1/bid-templates/{TEMPLATE_ID}").json()

    assert body["is_deletable"] is False
    assert body["is_in_use"] is True
    assert body["referencing_packages_total"] == 1
    assert body["referencing_packages"][0]["task_name"] == "Rough Grading"


def test_detail_mixed_live_and_cancelled(client_factory, active_trade):
    t = make_template()
    packages = [
        _detail_pkg(uuid4(), "Rough Grading", "open"),
        _detail_pkg(uuid4(), "Cancelled Scope", "cancelled"),
    ]
    client = client_factory(_db([t], packages, active_trade))
    body = client.get(f"/api/v1/bid-templates/{TEMPLATE_ID}").json()

    assert body["is_deletable"] is False
    assert body["is_in_use"] is True
    # Only the live one blocks the edit.
    assert body["referencing_packages_total"] == 1
    assert body["referencing_packages"][0]["status"] == "open"
