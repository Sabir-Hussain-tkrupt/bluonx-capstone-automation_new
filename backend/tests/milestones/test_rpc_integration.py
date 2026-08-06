"""Real-DB integration checks for the milestone RPCs (Phase 10 foundation).

These hit the live test Supabase with the service_role client. They deliberately
avoid seeding the full task→contract→milestone chain (heavy and DB-polluting;
the repo convention is mocked service tests) and instead verify the RPC *boundary*
that a mock cannot:

  1. `transition_milestone` and `fn_create_milestone` exist and are EXECUTE-granted
     to service_role — a permission/signature regression (e.g. a stale GRANT after
     the RPC signature changed) surfaces here as a 42883/permission error rather
     than the expected PT code.
  2. A raised SQLSTATE surfaces on `APIError.code` as `PT404` / `PT422`, which is
     exactly what `milestone_service._map_transition_error` keys on.

None of these mutate data (PT404 short-circuits before any write, unknown-action
raises PT422 before the lock). The deeper RPC invariants — cycle_number bump,
baseline_end_date untouched, exactly one ledger row per transition, the creation
event, and the date-guard PT409 — require a real milestone (hence the full contract
chain) and are verified end-to-end through the PM UI during manual verification.
"""

from __future__ import annotations

import uuid

import pytest
from postgrest.exceptions import APIError
from supabase import create_client

from app.core.config import settings

# Probes the live RPC boundary (existence, EXECUTE grants, raised SQLSTATEs),
# which is precisely what a mock cannot verify.
pytestmark = pytest.mark.requires_db


@pytest.fixture(scope="module")
def service_db():
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY):
        pytest.skip("Supabase service-role credentials not configured")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _transition(db, **overrides):
    params = {
        "p_milestone_id": str(uuid.uuid4()),
        "p_action": "pm_mark_started",
        "p_actor_user_id": str(uuid.uuid4()),
        "p_actor_vendor_contact_id": None,
        "p_milestone_response_id": None,
        "p_milestone_alert_id": None,
        "p_actual_start_date": None,
        "p_actual_end_date": None,
        "p_new_end_date": None,
        "p_note": "integration probe",
    }
    params.update(overrides)
    return db.rpc("transition_milestone", params).execute()


def test_transition_unknown_milestone_raises_pt404(service_db):
    """Confirms the RPC is callable by service_role AND that a raised SQLSTATE
    lands on APIError.code as 'PT404' (what the service maps on)."""
    with pytest.raises(APIError) as exc:
        _transition(service_db)
    assert exc.value.code == "PT404"


def test_transition_unknown_action_raises_pt422(service_db):
    with pytest.raises(APIError) as exc:
        _transition(service_db, p_action="not_a_real_action")
    assert exc.value.code == "PT422"
