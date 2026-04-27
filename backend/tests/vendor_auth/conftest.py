"""
Fixtures for the vendor-auth test suite.

Inserts real rows into Supabase (the user explicitly asked NOT to mock — gate
checks in the validate-token endpoint depend on actual SQL behavior). Each
fixture cleans up after itself so a failed test never leaves orphans behind.

Performance: parent rows (vendor, contact, project, task, template,
template_items) are session-scoped because they're invariant across every
gate test. Per-test work is limited to the rows that actually vary between
gate scenarios (bid_package, bid_invitation, magic_link_token), keeping
each test's network bill to ~5 round-trips against remote Supabase.

Conventions:
  - Seeded rows carry "vauth-test-{uuid}" markers so a stray row from a
    crashed test is easy to spot/scrub.
  - The throwaway protected endpoint (/api/v1/__vendor_auth_test__/protected)
    is mounted here at module import. Production code never imports this
    file, so the route only exists during pytest.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import Depends
from httpx import ASGITransport

from app.core.config import settings
from app.core.supabase_client import init_supabase
from app.core.vendor_auth import VendorContext, get_vendor_context
from app.main import app


# ── Throwaway protected endpoint (only exists under pytest) ─────────────


@app.get("/api/v1/__vendor_auth_test__/protected")
async def _vendor_protected(ctx: VendorContext = Depends(get_vendor_context)) -> dict:
    return {
        "vendor_id": str(ctx.vendor_id),
        "vendor_contact_id": str(ctx.vendor_contact_id),
        "bid_invitation_id": str(ctx.bid_invitation_id),
        "bid_package_id": str(ctx.bid_package_id),
        "task_id": str(ctx.task_id),
    }


# ── Core clients ────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def db():
    """Service-role Supabase client — bypasses RLS, like the API does.

    Also bound to `app.state.supabase` so requests routed through
    ASGITransport (which does not execute the FastAPI lifespan) still
    resolve `Depends(get_supabase)` correctly.
    """
    client = init_supabase(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    app.state.supabase = client
    return client


@pytest_asyncio.fixture
async def vendor_client(db):  # noqa: ARG001 — the dep ensures app.state is wired
    """httpx.AsyncClient bound to the FastAPI app via ASGITransport."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Each test starts with a clean limiter so per-IP buckets don't leak."""
    from app.core import rate_limit

    rate_limit._buckets.clear()
    yield
    rate_limit._buckets.clear()


# ── FK satisfaction (read-only refs to existing rows) ───────────────────


@pytest.fixture(scope="session")
def admin_user_id(db) -> str:
    rows = db.table("users").select("id").eq("role", "admin").limit(1).execute().data
    if not rows:
        pytest.skip("No admin user available for created_by FK")
    return rows[0]["id"]


@pytest.fixture(scope="session")
def trade_id(db) -> str:
    rows = db.table("trades").select("id").limit(1).execute().data
    if not rows:
        pytest.skip("No trade row available for tasks.trade_id FK")
    return rows[0]["id"]


# ── Session-scoped parent rows (created once, reused by every gate test) ─


@dataclass
class ParentRefs:
    vendor_id: str
    vendor_contact_id: str
    project_id: str
    task_id: str
    bid_template_id: str
    template_item_ids: list[str]


@pytest.fixture(scope="session")
def parent_seed(db, admin_user_id, trade_id) -> ParentRefs:
    """Insert the static FK chain once. Yield refs, drop everything at end."""
    marker = f"vauth-test-{uuid4().hex[:8]}"

    vendor = (
        db.table("vendors")
        .insert({"company_name": f"Test Vendor {marker}", "status": "active"})
        .execute()
        .data[0]
    )
    contact = (
        db.table("vendor_contacts")
        .insert(
            {
                "vendor_id": vendor["id"],
                "full_name": f"Contact {marker}",
                "email": f"{marker}@test.invalid",
                "is_primary": True,
            }
        )
        .execute()
        .data[0]
    )
    project = (
        db.table("projects")
        .insert(
            {
                "name": f"Test Project {marker}",
                "city": "Phoenix",
                "address": "1 Test St",
                "created_by": admin_user_id,
            }
        )
        .execute()
        .data[0]
    )
    task = (
        db.table("tasks")
        .insert(
            {
                "project_id": project["id"],
                "trade_id": trade_id,
                "name": f"Test Task {marker}",
                "description": "Site work for vendor-auth test",
                "phase": "development",
                "bid_type": "competitive",
                "created_by": admin_user_id,
            }
        )
        .execute()
        .data[0]
    )
    template = (
        db.table("bid_templates")
        .insert(
            {
                "name": f"Test Template {marker}",
                "is_lump_sum": False,
                "created_by": admin_user_id,
            }
        )
        .execute()
        .data[0]
    )
    items = (
        db.table("bid_template_items")
        .insert(
            [
                {
                    "bid_template_id": template["id"],
                    "description": "Mobilization",
                    "item_type": "lump_sum",
                    "sort_order": 1,
                },
                {
                    "bid_template_id": template["id"],
                    "description": "Earthwork",
                    "item_type": "unit_price",
                    "unit_of_measure": "CY",
                    "sort_order": 2,
                },
            ]
        )
        .execute()
        .data
    )

    refs = ParentRefs(
        vendor_id=vendor["id"],
        vendor_contact_id=contact["id"],
        project_id=project["id"],
        task_id=task["id"],
        bid_template_id=template["id"],
        template_item_ids=[item["id"] for item in items],
    )
    yield refs

    # Reverse FK order. bid_templates cascades template_items.
    db.table("bid_templates").delete().eq("id", template["id"]).execute()
    db.table("tasks").delete().eq("id", task["id"]).execute()
    db.table("projects").delete().eq("id", project["id"]).execute()
    db.table("vendor_contacts").delete().eq("id", contact["id"]).execute()
    db.table("vendors").delete().eq("id", vendor["id"]).execute()


# ── Per-test gate-shaping seed ──────────────────────────────────────────


@dataclass
class SeedRefs:
    """Identifiers for one gate scenario: package + invitation + token."""

    raw_token: str
    token_hash: str
    vendor_id: str
    vendor_contact_id: str
    project_id: str
    task_id: str
    bid_template_id: str
    template_item_ids: list[str]
    bid_package_id: str
    bid_invitation_id: str
    magic_link_token_id: str
    bid_submission_id: str | None = None


@dataclass
class _Tracker:
    bid_submissions: list[str] = field(default_factory=list)
    bid_invitations: list[str] = field(default_factory=list)
    bid_packages: list[str] = field(default_factory=list)


def _seed_gate(
    db,
    parents: ParentRefs,
    admin_id: str,
    *,
    package_status: str = "open",
    token_expires_in_hours: float = 24.0,
    token_is_used: bool = False,
    token_used_at: datetime | None = None,
) -> tuple[SeedRefs, _Tracker]:
    """Insert ONLY the rows that vary per test: bid_package + invitation + token."""
    tracker = _Tracker()

    deadline = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    package = (
        db.table("bid_packages")
        .insert(
            {
                "task_id": parents.task_id,
                "bid_template_id": parents.bid_template_id,
                "deadline": deadline,
                "status": package_status,
                "created_by": admin_id,
                "round_number": 1,
                "instructions": "Bid instructions for test",
            }
        )
        .execute()
        .data[0]
    )
    tracker.bid_packages.append(package["id"])

    invitation = (
        db.table("bid_invitations")
        .insert(
            {
                "bid_package_id": package["id"],
                "vendor_id": parents.vendor_id,
                "vendor_contact_id": parents.vendor_contact_id,
                "status": "sent",
            }
        )
        .execute()
        .data[0]
    )
    tracker.bid_invitations.append(invitation["id"])

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    token_expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=token_expires_in_hours)
    ).isoformat()
    token_row: dict[str, Any] = {
        "bid_invitation_id": invitation["id"],
        "vendor_id": parents.vendor_id,
        "token_hash": token_hash,
        "expires_at": token_expires_at,
        "is_used": token_is_used,
    }
    if token_used_at is not None:
        token_row["used_at"] = token_used_at.isoformat()
        token_row["ip_address"] = "203.0.113.99"
    token = db.table("magic_link_tokens").insert(token_row).execute().data[0]

    refs = SeedRefs(
        raw_token=raw_token,
        token_hash=token_hash,
        vendor_id=parents.vendor_id,
        vendor_contact_id=parents.vendor_contact_id,
        project_id=parents.project_id,
        task_id=parents.task_id,
        bid_template_id=parents.bid_template_id,
        template_item_ids=parents.template_item_ids,
        bid_package_id=package["id"],
        bid_invitation_id=invitation["id"],
        magic_link_token_id=token["id"],
    )
    return refs, tracker


def _teardown_gate(db, tracker: _Tracker) -> None:
    if tracker.bid_submissions:
        db.table("bid_submissions").delete().in_("id", tracker.bid_submissions).execute()
    if tracker.bid_invitations:
        # Cascades magic_link_tokens.
        db.table("bid_invitations").delete().in_("id", tracker.bid_invitations).execute()
    if tracker.bid_packages:
        db.table("bid_packages").delete().in_("id", tracker.bid_packages).execute()


@pytest.fixture
def seed(db, parent_seed, admin_user_id) -> Callable[..., SeedRefs]:
    """Factory — call with overrides to shape one gate scenario per test."""
    trackers: list[_Tracker] = []

    def _factory(**kwargs) -> SeedRefs:
        refs, tracker = _seed_gate(db, parent_seed, admin_user_id, **kwargs)
        trackers.append(tracker)
        return refs

    yield _factory

    for tracker in trackers:
        _teardown_gate(db, tracker)


# ── Convenience wrappers used by individual tests ───────────────────────


@pytest.fixture
def valid_token_setup(seed) -> SeedRefs:
    return seed()


@pytest.fixture
def expired_token_setup(seed) -> SeedRefs:
    return seed(token_expires_in_hours=-1)


@pytest.fixture
def used_token_setup(seed) -> SeedRefs:
    """Token already consumed — re-click should still succeed (per design)."""
    used_at = datetime.now(timezone.utc) - timedelta(hours=2)
    return seed(token_is_used=True, token_used_at=used_at)


@pytest_asyncio.fixture
async def submitted_bid_setup(db, seed):
    """Seed + a non-draft bid_submission. Teardown deletes the submission
    BEFORE the seed fixture's teardown deletes the invitation (RESTRICT FK).
    """
    refs = seed()
    submission = (
        db.table("bid_submissions")
        .insert(
            {
                "bid_invitation_id": refs.bid_invitation_id,
                "vendor_id": refs.vendor_id,
                "is_draft": False,
                "status": "submitted",
                "total_amount": "1000.00",
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .execute()
        .data[0]
    )
    refs.bid_submission_id = submission["id"]
    yield refs
    db.table("bid_submissions").delete().eq("id", submission["id"]).execute()
