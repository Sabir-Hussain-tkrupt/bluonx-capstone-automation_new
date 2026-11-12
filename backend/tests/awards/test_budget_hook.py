"""Financial module (Phase 2 · Task 2.5): the award → budget hook.

The award flow itself is unchanged; these tests pin that the budget hook runs
after the award is written and that NO budget failure can change the response.
"""

from __future__ import annotations

from app.services import budget_award_sync

from .conftest import award_body
from .test_create_award_gate import URL, clean_spec


def test_hook_receives_the_new_award(recording_client_factory, monkeypatch):
    seen = []
    monkeypatch.setattr(budget_award_sync, "safe_apply_award", lambda db, award: seen.append(award) or "applied")
    c, _calls = recording_client_factory(clean_spec())
    r = c.post(URL, json=award_body())
    assert r.status_code == 201
    assert len(seen) == 1
    assert seen[0]["award_amount"] == "50000.00"
    assert seen[0]["status"] == "pending_acceptance"


def test_budget_failure_never_changes_the_award_response(recording_client_factory, monkeypatch):
    baseline_client, _ = recording_client_factory(clean_spec())
    baseline = baseline_client.post(URL, json=award_body())

    def boom(*_a, **_k):
        raise RuntimeError("budget service exploded")

    # The real safe wrapper must swallow anything the core function raises.
    monkeypatch.setattr(budget_award_sync, "apply_award", boom)
    c, _ = recording_client_factory(clean_spec())
    r = c.post(URL, json=award_body())
    assert r.status_code == baseline.status_code == 201
    body, expected = r.json(), baseline.json()
    for key in ("status", "award_amount", "task_id", "vendor_id", "envelope_sent"):
        assert body[key] == expected[key]
