"""Phase 2 · Task 2.5 — award / DocuSign → budget line hooks."""

import asyncio
from unittest.mock import patch

from app.routers import docusign_webhooks
from app.services import budget_award_sync as sync
from tests.financial._memdb import MemDB, api_error
from tests.financial.conftest import ADMIN

P, T, L, A, A_OLD, C = "p1", "t1", "l1", "a1", "a0", "c1"


def base_db(**over):
    tables = {
        "projects": [{"id": P, "budget_status": "baselined"}],
        "budget_lines": [{"id": L, "project_id": P, "task_id": T, "line_type": "bid_activity",
                          "award_id": None, "committed_amount": "0", "is_locked": False,
                          "contract_id": None, "deleted_at": None}],
        "awards": [{"id": A, "task_id": T, "award_amount": "52000.00", "awarded_by": "u-pm",
                    "status": "pending_acceptance"}],
        "contracts": [{"id": C, "task_id": T, "award_id": A, "status": "executed"}],
    }
    tables.update(over)
    return MemDB(tables)


class TestApply:
    def test_applies_award_amount_to_task_line(self):
        db = base_db()
        assert sync.apply_award(db, db.tables["awards"][0]) == "applied"
        (params,) = db.calls("fn_apply_bid_to_line")
        assert params == {"p_budget_line_id": L, "p_award_id": A, "p_amount": "52000.00", "p_actor": "u-pm"}

    def test_skips_projects_without_budget(self):
        db = base_db(projects=[{"id": P, "budget_status": "none"}])
        assert sync.apply_award(db, db.tables["awards"][0]) == "skipped"
        assert db.rpc_calls == []

    def test_skips_tasks_without_line(self):
        db = base_db(budget_lines=[])
        assert sync.apply_award(db, db.tables["awards"][0]) == "skipped"

    def test_idempotent_when_already_applied(self):
        db = base_db()
        db.tables["budget_lines"][0].update(award_id=A, committed_amount="52000.00")
        assert sync.apply_award(db, db.tables["awards"][0]) == "unchanged"
        assert db.rpc_calls == []


class TestReverseAndLock:
    def test_reverse_uses_line_carrying_the_award(self):
        db = base_db()
        db.tables["budget_lines"][0]["award_id"] = A
        assert sync.reverse_award(db, A, None, "DocuSign envelope declined") == "reversed"
        (params,) = db.calls("fn_reverse_bid_on_line")
        assert params["p_budget_line_id"] == L and params["p_reason"] == "DocuSign envelope declined"
        assert params["p_actor"] == "u-pm"

    def test_reverse_nothing_applied_is_skipped(self):
        assert sync.reverse_award(base_db(), A) == "skipped"

    def test_lock_applies_missing_award_first(self):
        db = base_db()
        assert sync.lock_for_contract(db, db.tables["contracts"][0]) == "locked"
        assert [n for n, _ in db.rpc_calls] == ["fn_apply_bid_to_line", "fn_lock_budget_line"]

    def test_lock_idempotent(self):
        db = base_db()
        db.tables["budget_lines"][0].update(award_id=A, committed_amount="52000.00", is_locked=True, contract_id=C)
        assert sync.lock_for_contract(db, db.tables["contracts"][0]) == "unchanged"
        assert db.rpc_calls == []


class TestSafeWrappersNeverRaise:
    def test_db_error_is_swallowed_and_logged(self, caplog):
        db = base_db()
        db.rpc_handlers["fn_apply_bid_to_line"] = lambda p: api_error("PT409", "Project is on hold")
        assert sync.safe_apply_award(db, db.tables["awards"][0]) == "failed"
        assert "Sync awards" in caplog.text

    def test_any_exception_is_swallowed(self):
        class Broken:
            def table(self, *_a):
                raise RuntimeError("network down")
        assert sync.safe_apply_award(Broken(), {"id": A, "task_id": T}) == "failed"
        assert sync.safe_reverse_award(Broken(), A, "x") == "failed"
        assert sync.safe_lock_for_contract(Broken(), C) == "failed"


class TestSyncProject:
    def test_back_fills_award_and_lock(self):
        db = base_db()
        assert sync.sync_project(db, P, "admin") == {"applied": 1, "locked": 1, "failed": 0}

    def test_reverses_declined_award_then_applies_new(self):
        db = base_db()
        db.tables["budget_lines"][0]["award_id"] = A_OLD
        db.tables["awards"].append({"id": A_OLD, "task_id": T, "award_amount": "1", "awarded_by": "u",
                                    "status": "declined_by_vendor"})
        db.tables["contracts"] = []
        out = sync.sync_project(db, P, "admin")
        assert [n for n, _ in db.rpc_calls] == ["fn_reverse_bid_on_line", "fn_apply_bid_to_line"]
        assert out["applied"] == 1

    def test_failures_counted_not_raised(self):
        db = base_db()
        db.rpc_handlers["fn_apply_bid_to_line"] = lambda p: api_error("PT409", "locked")
        assert sync.sync_project(db, P, "admin")["failed"] == 1

    def test_endpoint(self, fin_client):
        db = base_db(projects=[{"id": "11111111-1111-1111-1111-111111111111", "budget_status": "baselined",
                                "deleted_at": None}])
        resp = fin_client(db, ADMIN).post("/api/v1/projects/11111111-1111-1111-1111-111111111111/budget/sync-awards")
        assert resp.status_code == 200
        assert set(resp.json()) == {"applied", "locked", "failed"}


# ── The hooks are wired into the existing flows without changing them ──────
class TestWebhookWiring:
    def _env(self):
        return {
            "id": "e1", "status": "sent", "contract_id": C,
            "contracts": {"id": C, "status": "sent_for_signature", "award_id": A,
                          "awards": {"id": A, "status": "pending_acceptance", "vendor_id": "v", "task_id": T,
                                     "bid_submission_id": "s", "contract_valid_days": 365,
                                     "bid_submissions": {"bid_invitations": {"bid_package_id": None}}}},
        }

    def test_completed_calls_lock_and_result_unchanged_on_failure(self):
        db = MemDB({"docusign_envelopes": [self._env() | {"envelope_id": "env1"}], "awards": [], "contracts": []})
        with patch.object(docusign_webhooks.contract_service, "mark_contract_executed"), \
             patch.object(sync, "safe_lock_for_contract", return_value="failed") as hook:
            out = asyncio.run(docusign_webhooks.handle_envelope_event(
                envelope_id="env1", status="completed", payload={}, db=db))
        assert out == "applied"
        hook.assert_called_once_with(db, C)

    def test_declined_calls_reverse(self):
        db = MemDB({"docusign_envelopes": [self._env() | {"envelope_id": "env1"}], "awards": []})
        with patch.object(docusign_webhooks.contract_service, "mark_contract_terminated"), \
             patch.object(sync, "safe_reverse_award", return_value="reversed") as hook:
            out = asyncio.run(docusign_webhooks.handle_envelope_event(
                envelope_id="env1", status="declined", payload={}, db=db))
        assert out == "applied"
        hook.assert_called_once_with(db, A, "DocuSign envelope declined")

    # The award-creation hook is exercised end to end in tests/awards/test_budget_hook.py
    # (it needs the award fixtures that live in that package).
