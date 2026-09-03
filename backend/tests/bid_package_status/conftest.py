"""Real-DB fixtures for the cancel-bid-package suite.

The mocked sibling suite (test_cancel_bid_package.py) cannot observe a write
that never happens, which is exactly how the missing tasks.status reset shipped
green. These fixtures seed real rows through the service-role client so the
DB-visible outcome of a cancel can be asserted directly.

Follows the tests/vendor_auth/conftest.py pattern with one deliberate
difference: the TASK is per-test, not session-scoped. Cancelling mutates
tasks.status, so a shared task would leak state between tests. Only the
invariant parents (vendor, contact, project, template) are session-scoped.

Every seeded row is tracked on the Scenario and torn down in reverse-FK order.
Rows carry a "cancelpkg-test-{hex}" marker so a stray row from a crashed run is
easy to spot.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

import pytest
from supabase import create_client

from app.core.config import settings


# ── Core client ─────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def db():
    """Service-role Supabase client, the same one the API writes through."""
    if not (settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY):
        pytest.skip("Supabase service-role credentials not configured")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


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


# ── Session-scoped parents (invariant across every scenario) ────────────


@dataclass
class ParentRefs:
    vendor_id: str
    vendor_contact_id: str
    project_id: str
    bid_template_id: str


@pytest.fixture(scope="session")
def parents(db, admin_user_id) -> ParentRefs:
    """Insert the static FK chain once. No task here: see the module docstring."""
    marker = f"cancelpkg-test-{uuid4().hex[:8]}"

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
    template = (
        db.table("bid_templates")
        .insert(
            {
                "name": f"Test Template {marker}",
                "is_lump_sum": True,
                "created_by": admin_user_id,
            }
        )
        .execute()
        .data[0]
    )

    yield ParentRefs(
        vendor_id=vendor["id"],
        vendor_contact_id=contact["id"],
        project_id=project["id"],
        bid_template_id=template["id"],
    )

    # Reverse FK order. bid_templates cascades its items.
    db.table("bid_templates").delete().eq("id", template["id"]).execute()
    db.table("projects").delete().eq("id", project["id"]).execute()
    db.table("vendor_contacts").delete().eq("id", contact["id"]).execute()
    db.table("vendors").delete().eq("id", vendor["id"]).execute()


# ── Per-test scenario ───────────────────────────────────────────────────


@dataclass
class Tracker:
    """Ids to delete, per table. Teardown walks these in reverse-FK order."""

    awards: list[str] = field(default_factory=list)
    magic_link_tokens: list[str] = field(default_factory=list)
    bid_revision_requests: list[str] = field(default_factory=list)
    bid_submissions: list[str] = field(default_factory=list)
    bid_invitations: list[str] = field(default_factory=list)
    bid_packages: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    vendor_contacts: list[str] = field(default_factory=list)
    vendors: list[str] = field(default_factory=list)


@dataclass
class Scenario:
    """One task plus its packages. Ids only; tests re-read state from the DB."""

    task_id: str
    package_ids: list[str]
    project_id: str
    vendor_id: str
    vendor_contact_id: str
    bid_template_id: str
    admin_user_id: str
    tracker: Tracker

    @property
    def package_id(self) -> str:
        """The first package. Sugar for the single-package scenarios."""
        return self.package_ids[0]


# Reverse-FK teardown order. magic_link_tokens go before
# bid_revision_requests: they CASCADE from bid_invitations but RESTRICT on
# bid_revision_request_id, so a revision token would block the request delete.
# vendors go last: bid_invitations, bid_submissions, awards and
# magic_link_tokens all RESTRICT against them.
_TEARDOWN_ORDER = (
    "awards",
    "magic_link_tokens",
    "bid_revision_requests",
    "bid_submissions",
    "bid_invitations",
    "bid_packages",
    "tasks",
    "vendor_contacts",
    "vendors",
)


def _teardown(db, tracker: Tracker) -> None:
    for table in _TEARDOWN_ORDER:
        ids = getattr(tracker, table)
        if ids:
            db.table(table).delete().in_("id", ids).execute()


def future_iso(days: int = 7) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.fixture
def scenario(db, parents, admin_user_id, trade_id) -> Callable[..., Scenario]:
    """Factory: one fresh task plus a package per entry in `package_statuses`.

    task_status is applied after insert (tasks always land as 'draft'), so a
    test can stage 'bidding', 'awarded', or anything else the guard must respect.
    """
    trackers: list[Tracker] = []

    def _factory(
        *,
        package_statuses: tuple[str, ...] = ("open",),
        task_status: str = "bidding",
        bid_type: str = "competitive",
    ) -> Scenario:
        tracker = Tracker()
        trackers.append(tracker)
        marker = uuid4().hex[:8]

        task = (
            db.table("tasks")
            .insert(
                {
                    "project_id": parents.project_id,
                    "trade_id": trade_id,
                    "name": f"Cancel Task {marker}",
                    "description": "Cancel-path fixture task",
                    "phase": "development",
                    "bid_type": bid_type,
                    "created_by": admin_user_id,
                }
            )
            .execute()
            .data[0]
        )
        tracker.tasks.append(task["id"])

        if task_status != "draft":
            db.table("tasks").update({"status": task_status}).eq(
                "id", task["id"]
            ).execute()

        package_ids: list[str] = []
        for pkg_status in package_statuses:
            pkg = (
                db.table("bid_packages")
                .insert(
                    {
                        "task_id": task["id"],
                        "bid_template_id": parents.bid_template_id,
                        "deadline": future_iso(),
                        "status": pkg_status,
                        "created_by": admin_user_id,
                        "instructions": f"Round for {marker}",
                    }
                )
                .execute()
                .data[0]
            )
            tracker.bid_packages.append(pkg["id"])
            package_ids.append(pkg["id"])

        return Scenario(
            task_id=task["id"],
            package_ids=package_ids,
            project_id=parents.project_id,
            vendor_id=parents.vendor_id,
            vendor_contact_id=parents.vendor_contact_id,
            bid_template_id=parents.bid_template_id,
            admin_user_id=admin_user_id,
            tracker=tracker,
        )

    yield _factory

    for tracker in trackers:
        _teardown(db, tracker)


# ── Row builders for the richer scenarios ───────────────────────────────


def _new_vendor(db, tracker: Tracker) -> tuple[str, str]:
    """A fresh vendor plus primary contact.

    One per invitation, because bid_invitations is UNIQUE on
    (bid_package_id, vendor_id): a package cannot invite the same vendor twice.
    """
    marker = f"cancelpkg-test-{uuid4().hex[:8]}"
    vendor = (
        db.table("vendors")
        .insert({"company_name": f"Test Vendor {marker}", "status": "active"})
        .execute()
        .data[0]
    )
    tracker.vendors.append(vendor["id"])
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
    tracker.vendor_contacts.append(contact["id"])
    return vendor["id"], contact["id"]


@pytest.fixture
def add_invitation(db) -> Callable[..., dict]:
    """Attach an invitation, and optionally its magic-link token, to a package.

    Mints its own vendor, so several invitations can share one package. Returns
    the invitation row, carrying `token_id` when a token was created.
    """

    def _add(
        sc: Scenario,
        *,
        package_id: str | None = None,
        status: str = "sent",
        with_token: bool = False,
    ) -> dict:
        vendor_id, contact_id = _new_vendor(db, sc.tracker)
        invitation = (
            db.table("bid_invitations")
            .insert(
                {
                    "bid_package_id": package_id or sc.package_id,
                    "vendor_id": vendor_id,
                    "vendor_contact_id": contact_id,
                    "status": status,
                }
            )
            .execute()
            .data[0]
        )
        sc.tracker.bid_invitations.append(invitation["id"])

        if with_token:
            raw = secrets.token_urlsafe(32)
            token = (
                db.table("magic_link_tokens")
                .insert(
                    {
                        "bid_invitation_id": invitation["id"],
                        "vendor_id": vendor_id,
                        "token_hash": hashlib.sha256(raw.encode()).hexdigest(),
                        "expires_at": future_iso(),
                        "is_used": False,
                    }
                )
                .execute()
                .data[0]
            )
            sc.tracker.magic_link_tokens.append(token["id"])
            invitation["token_id"] = token["id"]

        return invitation

    return _add


@pytest.fixture
def add_submission(db) -> Callable[..., dict]:
    """A finalized (non-draft) submission on an invitation.

    Takes the invitation ROW, not its id: fn_enforce_submission_vendor_consistency
    requires bid_submissions.vendor_id to equal the invitation's.
    """

    def _add(sc: Scenario, invitation: dict, *, amount: str = "1000.00") -> dict:
        submission = (
            db.table("bid_submissions")
            .insert(
                {
                    "bid_invitation_id": invitation["id"],
                    "vendor_id": invitation["vendor_id"],
                    "is_draft": False,
                    "status": "submitted",
                    "total_amount": amount,
                    "submitted_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .execute()
            .data[0]
        )
        sc.tracker.bid_submissions.append(submission["id"])
        return submission

    return _add


@pytest.fixture
def add_revision_request(db) -> Callable[..., dict]:
    """A pending revision request plus its own magic-link token.

    The token carries bid_revision_request_id, which is what makes it a
    revision token: cancel_bid_package must revoke it, because a revision token
    is validated against its own status and deadline, never the package status.
    """

    def _add(
        sc: Scenario,
        invitation: dict,
        submission: dict,
        *,
        status: str = "pending",
    ) -> dict:
        request = (
            db.table("bid_revision_requests")
            .insert(
                {
                    "bid_invitation_id": invitation["id"],
                    "original_submission_id": submission["id"],
                    "pm_note": "Please revise the mobilization line.",
                    "revision_deadline": future_iso(3),
                    "status": status,
                    "requested_by": sc.admin_user_id,
                }
            )
            .execute()
            .data[0]
        )
        sc.tracker.bid_revision_requests.append(request["id"])

        raw = secrets.token_urlsafe(32)
        token = (
            db.table("magic_link_tokens")
            .insert(
                {
                    "bid_invitation_id": invitation["id"],
                    "vendor_id": invitation["vendor_id"],
                    "token_hash": hashlib.sha256(raw.encode()).hexdigest(),
                    "expires_at": future_iso(3),
                    "is_used": False,
                    "bid_revision_request_id": request["id"],
                }
            )
            .execute()
            .data[0]
        )
        sc.tracker.magic_link_tokens.append(token["id"])
        request["token_id"] = token["id"]
        return request

    return _add


@pytest.fixture
def add_award(db) -> Callable[..., dict]:
    """An award on the task, used to exercise the award guard.

    Inserted directly rather than through fn_create_award, which would also flip
    the task to 'awarded' and confound what these tests are measuring.
    """

    def _add(
        sc: Scenario,
        submission: dict,
        *,
        status: str = "pending_acceptance",
        amount: str = "1000.00",
    ) -> dict:
        award = (
            db.table("awards")
            .insert(
                {
                    "task_id": sc.task_id,
                    "bid_submission_id": submission["id"],
                    "vendor_id": submission["vendor_id"],
                    "awarded_by": sc.admin_user_id,
                    "award_amount": amount,
                    "status": status,
                }
            )
            .execute()
            .data[0]
        )
        sc.tracker.awards.append(award["id"])
        return award

    return _add
