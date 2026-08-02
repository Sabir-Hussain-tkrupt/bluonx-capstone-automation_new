"""
Intelligent vendor filtering service for competitive bidding.

Runs a multi-stage pipeline to find qualified vendors for a task,
ordered cheapest-to-most-expensive filters. Returns qualified and
disqualified vendors with detailed reasons.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.models.vendor_filtering import (
    FilterCriteria,
    FilteredVendor,
    QualifiedVendorsResponse,
    VendorPrimaryContact,
)
from app.services.distance import haversine_distance, routes_api_distance
from app.services.insurance_rules import classify_insurance

logger = logging.getLogger(__name__)


async def filter_qualified_vendors(
    db: Client,
    task_id: str,
    radius_miles: float = 75,
    include_flagged: bool = True,
) -> QualifiedVendorsResponse:
    """Run the full vendor filtering pipeline for a task.

    Raises:
        ValueError: If task not found, deleted, or is internal type.
    """
    warnings: list[str] = []

    # ── 1. Load task ────────────────────────────────────────────────────
    try:
        task_resp = (
            db.table("tasks")
            .select("id, name, trade_id, bid_type, budget_estimate, project_id")
            .eq("id", task_id)
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
    except APIError:
        raise ValueError("Task not found")
    if not task_resp.data:
        raise ValueError("Task not found")

    task = task_resp.data

    # Positive gate (mirrors bid_package_service): only a competitive task
    # accepts bids. Anything else, including a legacy 'direct_assign' row, is
    # turned away before vendors are ever filtered for it.
    if task["bid_type"] != "competitive":
        raise ValueError(
            f"Only competitive tasks accept bids (bid_type={task['bid_type']!r})."
        )

    trade_id = task["trade_id"]
    budget_estimate = (
        Decimal(str(task["budget_estimate"])) if task.get("budget_estimate") else None
    )

    # ── 2. Load project ────────────────────────────────────────────────
    try:
        project_resp = (
            db.table("projects")
            .select("id, name, latitude, longitude, estimated_end_date")
            .eq("id", task["project_id"])
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
    except APIError:
        raise ValueError("Project not found")
    if not project_resp.data:
        raise ValueError("Project not found")

    project = project_resp.data
    proj_lat = float(project["latitude"]) if project.get("latitude") else None
    proj_lng = float(project["longitude"]) if project.get("longitude") else None
    has_project_coords = proj_lat is not None and proj_lng is not None

    if not has_project_coords:
        warnings.append("Project has no coordinates; distance filter skipped")

    # Insurance horizon: the project end date if known, else no horizon.
    # The hard "expired" check is against today (below); project_end drives
    # only the softer "lapses before the project ends" advisory. Keeping these
    # separate is the fix for the old single-cutoff bug, where an overdue
    # project (past estimated_end_date) pushed the cutoff into the past and let
    # a vendor whose insurance had already lapsed still qualify.
    today = date.today()
    project_end = (
        date.fromisoformat(project["estimated_end_date"])
        if project.get("estimated_end_date")
        else None
    )
    # Reported in filter_criteria as the coverage horizon (informational).
    insurance_cutoff = project_end if project_end is not None else today

    # ── 3. Load trade name ──────────────────────────────────────────────
    try:
        trade_resp = (
            db.table("trades")
            .select("id, name")
            .eq("id", trade_id)
            .single()
            .execute()
        )
        trade_name = trade_resp.data["name"] if trade_resp.data else None
    except APIError:
        trade_name = None

    # ── 4. Trade match — fetch vendors with this trade ──────────────────
    vt_resp = (
        db.table("vendor_trades")
        .select("vendor_id")
        .eq("trade_id", trade_id)
        .execute()
    )
    vendor_ids = [r["vendor_id"] for r in (vt_resp.data or [])]

    if not vendor_ids:
        return _build_response(
            task, project, trade_name, insurance_cutoff, budget_estimate,
            radius_miles, [], [], warnings,
        )

    # Fetch full vendor rows for matched IDs
    vendors_resp = (
        db.table("vendors")
        .select("*")
        .in_("id", vendor_ids)
        .is_("deleted_at", "null")
        .execute()
    )
    vendors = vendors_resp.data or []

    if not vendors:
        return _build_response(
            task, project, trade_name, insurance_cutoff, budget_estimate,
            radius_miles, [], [], warnings,
        )

    # ── 5. In-memory filtering pipeline ─────────────────────────────────
    qualified_raw: list[dict] = []
    disqualified_raw: list[dict] = []

    for v in vendors:
        reasons: list[str] = []
        advisories: list[str] = []

        # 5a. Status check
        if v.get("status") != "active":
            reasons.append("inactive_status")

        # 5b. Onboarding check
        if v.get("onboarding_status") != "complete":
            reasons.append("onboarding_incomplete")

        # 5c. Insurance check. Two severities, one classifier (shared with
        #     pre-award so the stages never disagree): a lapsed certificate
        #     disqualifies, but one that is valid today and merely ends before
        #     the project's estimated end is a non-blocking advisory — the
        #     vendor stays selectable.
        ins_date_str = v.get("insurance_expiration_date")
        ins_date = date.fromisoformat(str(ins_date_str)) if ins_date_str else None
        ins_status = classify_insurance(ins_date, project_end, today)
        if ins_status == "missing":
            reasons.append("insurance_missing")
        elif ins_status == "expired":
            reasons.append("insurance_expired")
        elif ins_status == "lapses_before_end":
            advisories.append("insurance_lapses_before_project_end")

        # 5d. Bonding check
        if budget_estimate is not None and v.get("bonding_capacity") is not None:
            if Decimal(str(v["bonding_capacity"])) < budget_estimate:
                reasons.append("insufficient_bonding")

        # 5e. Capacity check
        max_jobs = v.get("max_active_jobs")
        current_jobs = v.get("current_active_jobs", 0)
        if max_jobs is not None and current_jobs >= max_jobs:
            reasons.append("over_capacity")

        # Advisories are orthogonal to qualification: a vendor can be qualified
        # with an advisory, or disqualified for another reason yet still carry
        # one. Both buckets keep the advisories list.
        entry = {"vendor": v, "reasons": reasons, "advisories": advisories}
        if reasons:
            disqualified_raw.append(entry)
        else:
            qualified_raw.append(entry)

    # ── 6. Distance filter (only on qualified set) ──────────────────────
    if has_project_coords and qualified_raw:
        still_qualified: list[dict] = []
        buffer_radius = radius_miles * 1.33
        # Per-request circuit breaker for the Routes API. See the note below.
        routes_api_available = True

        for entry in qualified_raw:
            v = entry["vendor"]
            v_lat = float(v["latitude"]) if v.get("latitude") else None
            v_lng = float(v["longitude"]) if v.get("longitude") else None

            if v_lat is None or v_lng is None:
                entry["distance_miles"] = None
                still_qualified.append(entry)
                continue

            # Haversine pre-filter (cheap)
            h_dist = haversine_distance(proj_lat, proj_lng, v_lat, v_lng)
            if h_dist is not None and h_dist > buffer_radius:
                entry["reasons"].append("outside_radius")
                disqualified_raw.append(entry)
                continue

            # Precise (driving) distance, unless the Routes API has already
            # failed once in this request. Each call carries its own 10s
            # timeout, so without this breaker a misconfigured or unreachable
            # Routes API costs 10s PER VENDOR: 20 qualified vendors becomes a
            # 200-second request that no browser or proxy will wait for. One
            # failure is enough to conclude it is unavailable right now, so the
            # rest of the cohort goes straight to Haversine.
            #
            # routes_api_distance is called directly rather than through
            # calculate_distance because it returns None on failure, whereas
            # calculate_distance silently substitutes the Haversine value and
            # leaves no way to tell a successful call from a fallback.
            dist = None
            if routes_api_available:
                dist = await routes_api_distance(proj_lat, proj_lng, v_lat, v_lng)
                if dist is None:
                    routes_api_available = False
                    logger.warning(
                        "Routes API unavailable for task %s; using straight-line "
                        "distance for the remaining vendors. Driving distance "
                        "typically runs 1.2-1.4x straight-line, so vendors near "
                        "the radius edge may be included when they are out of "
                        "range by road.",
                        task_id,
                    )
                    warnings.append(
                        "Driving distances were unavailable, so straight-line "
                        "distance was used. Vendors near the radius edge may be "
                        "further than they appear."
                    )
            if dist is None:
                dist = h_dist

            if dist is not None and dist > radius_miles:
                entry["reasons"].append("outside_radius")
                disqualified_raw.append(entry)
                continue

            entry["distance_miles"] = round(dist, 1) if dist is not None else None
            still_qualified.append(entry)

        qualified_raw = still_qualified
    else:
        # No project coords — everyone gets null distance
        for entry in qualified_raw:
            entry["distance_miles"] = None

    # Also compute distance for disqualified vendors (informational)
    if has_project_coords:
        for entry in disqualified_raw:
            v = entry["vendor"]
            v_lat = float(v["latitude"]) if v.get("latitude") else None
            v_lng = float(v["longitude"]) if v.get("longitude") else None
            if v_lat is not None and v_lng is not None:
                dist = haversine_distance(proj_lat, proj_lng, v_lat, v_lng)
                entry["distance_miles"] = round(dist, 1) if dist is not None else None
            else:
                entry["distance_miles"] = None
    else:
        for entry in disqualified_raw:
            entry["distance_miles"] = None

    # ── 7. Batch fetch flags ────────────────────────────────────────────
    all_vendor_ids = [e["vendor"]["id"] for e in qualified_raw + disqualified_raw]
    flags_by_vendor: dict[str, list[str]] = {}

    if all_vendor_ids:
        flags_resp = (
            db.table("vendor_flags")
            .select("vendor_id, reason")
            .in_("vendor_id", all_vendor_ids)
            .eq("is_resolved", False)
            .execute()
        )
        for f in (flags_resp.data or []):
            flags_by_vendor.setdefault(f["vendor_id"], []).append(f["reason"])

    # ── 8. Batch fetch contacts ─────────────────────────────────────────
    contacts_by_vendor: dict[str, list[dict]] = {}

    if all_vendor_ids:
        contacts_resp = (
            db.table("vendor_contacts")
            .select("id, vendor_id, full_name, email, phone, is_primary")
            .in_("vendor_id", all_vendor_ids)
            .execute()
        )
        for c in (contacts_resp.data or []):
            contacts_by_vendor.setdefault(c["vendor_id"], []).append(c)

    # ── 9. Check active bid package ─────────────────────────────────────
    bp_resp = (
        db.table("bid_packages")
        .select("id, round_number, status")
        .eq("task_id", task_id)
        .in_("status", ["open", "evaluating"])
        .execute()
    )
    if bp_resp.data:
        round_num = bp_resp.data[0].get("round_number", 1)
        warnings.append(
            f"Task already has an active bid package (round {round_num})"
        )

    # ── 10. Build FilteredVendor objects ────────────────────────────────
    def _build_vendor(entry: dict, status: str) -> FilteredVendor:
        v = entry["vendor"]
        vid = v["id"]
        reasons = entry["reasons"]
        dist = entry.get("distance_miles")

        # Contact resolution
        contact: VendorPrimaryContact | None = None
        contact_warning: str | None = None
        vendor_contacts = contacts_by_vendor.get(vid, [])

        if vendor_contacts:
            primary = next((c for c in vendor_contacts if c.get("is_primary")), None)
            chosen = primary or vendor_contacts[0]
            contact = VendorPrimaryContact(
                id=chosen["id"],
                full_name=chosen["full_name"],
                email=chosen["email"],
                phone=chosen.get("phone"),
            )
        else:
            contact_warning = "no_contact_on_file"

        # Insurance calculations
        ins_date_str = v.get("insurance_expiration_date")
        ins_date = date.fromisoformat(str(ins_date_str)) if ins_date_str else None
        ins_days = (ins_date - date.today()).days if ins_date else None

        # Capacity
        max_jobs = v.get("max_active_jobs")
        current_jobs = v.get("current_active_jobs", 0)
        available = (max_jobs - current_jobs) if max_jobs is not None else None

        # Flags
        vendor_flags = flags_by_vendor.get(vid, [])

        return FilteredVendor(
            vendor_id=vid,
            company_name=v["company_name"],
            primary_contact=contact,
            contact_warning=contact_warning,
            distance_miles=dist,
            insurance_expiration_date=ins_date,
            insurance_days_remaining=ins_days,
            bonding_capacity=Decimal(str(v["bonding_capacity"])) if v.get("bonding_capacity") else None,
            max_active_jobs=max_jobs,
            current_active_jobs=current_jobs,
            available_capacity=available,
            onboarding_status=v.get("onboarding_status", "pending"),
            has_unresolved_flags=len(vendor_flags) > 0,
            unresolved_flag_count=len(vendor_flags),
            flag_reasons=vendor_flags,
            qualification_status=status,
            disqualification_reasons=reasons,
            advisories=entry.get("advisories", []),
        )

    qualified = [_build_vendor(e, "qualified") for e in qualified_raw]
    disqualified = [_build_vendor(e, "disqualified") for e in disqualified_raw]

    # Filter out flagged vendors from qualified if include_flagged is False
    if not include_flagged:
        flagged_out = [v for v in qualified if v.has_unresolved_flags]
        qualified = [v for v in qualified if not v.has_unresolved_flags]
        # Move them to disqualified with reason
        for v in flagged_out:
            v.qualification_status = "disqualified"
            v.disqualification_reasons.append("has_unresolved_flags")
            disqualified.append(v)

    # Sort qualified by distance (nulls last)
    qualified.sort(key=lambda v: (v.distance_miles is None, v.distance_miles or 0))

    return _build_response(
        task, project, trade_name, insurance_cutoff, budget_estimate,
        radius_miles, qualified, disqualified, warnings,
    )


def _build_response(
    task: dict,
    project: dict,
    trade_name: str | None,
    insurance_cutoff: date,
    budget_estimate: Decimal | None,
    radius_miles: float,
    qualified: list[FilteredVendor],
    disqualified: list[FilteredVendor],
    warnings: list[str],
) -> QualifiedVendorsResponse:
    """Assemble the final response envelope."""
    return QualifiedVendorsResponse(
        task_id=task["id"],
        task_name=task["name"],
        trade_name=trade_name,
        project_id=project["id"],
        project_name=project["name"],
        filter_criteria=FilterCriteria(
            radius_miles=radius_miles,
            trade_id=task["trade_id"],
            trade_name=trade_name,
            min_bonding=budget_estimate,
            insurance_cutoff_date=insurance_cutoff,
        ),
        qualified_vendors=qualified,
        disqualified_vendors=disqualified,
        total_qualified=len(qualified),
        total_disqualified=len(disqualified),
        warnings=warnings,
    )
