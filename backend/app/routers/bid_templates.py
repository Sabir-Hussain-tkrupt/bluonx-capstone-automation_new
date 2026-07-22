"""Bid Template endpoints - /api/v1/bid-templates"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from postgrest.exceptions import APIError
from supabase import Client

from app.core.auth import get_current_active_user
from app.core.query_filters import escape_like_pattern
from app.core.supabase_client import get_supabase
from app.models.bid_templates import (
    BidTemplateCreate,
    BidTemplateDetailResponse,
    BidTemplateListResponse,
    BidTemplateUpdate,
)

# Statuses that count as a "live" bid_package reference. The enum is
# (open, closed, evaluating, cancelled). Anything not cancelled means a
# vendor round has been committed against this template and editing it
# would break bid comparability mid-round. See Task 8.1.
_LIVE_PACKAGE_STATUSES = ("open", "closed", "evaluating")

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Helpers ─────────────────────────────────────────────────────────────


#: Returned instead of the driver's text whenever Postgres rejects a write.
#: The raw exc.message leaks schema/constraint internals to the client; the
#: full exception still goes to the log.
_DB_REJECTED_DETAIL = (
    "The submitted data was rejected. Please review the values and try again."
)


def _parse_uuid(value: str, field_name: str = "id") -> UUID:
    """Parse a string as UUID, raise 422 if invalid.

    422 (not 400) so a malformed UUID in a query param matches what FastAPI
    already returns for a malformed UUID in the path — one class of error,
    one status code.
    """
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid {field_name}: '{value}' is not a valid UUID",
        )


def _get_template_or_404(db: Client, template_id: UUID) -> dict:
    """Fetch a bid template by ID, raise 404 if not found.

    Uses maybe_single(), not single(): PostgREST's single() raises an
    APIError (PGRST116) on zero rows, so "not found" had to be recovered by
    string-matching the driver's error text — which silently turns into a 502
    the moment that text changes. With maybe_single() a missing row returns
    data=None (and the response object itself may be None), which we translate
    into a clean 404. Matches _get_vendor_or_404 in routers/vendors.py.
    """
    try:
        response = (
            db.table("bid_templates")
            .select("*")
            .eq("id", str(template_id))
            .maybe_single()
            .execute()
        )
    except APIError as exc:
        logger.error("Supabase query failed for bid_templates: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch bid template from database",
        ) from exc

    if not response or not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bid template not found",
        )
    return response.data


def _enrich_templates_batched(db: Client, templates: list[dict]) -> list[dict]:
    """Attach trade_name, item_count and is_in_use to a page of templates.

    The per-row path (_build_template_response) fires three queries each —
    trade, item count, and referencing packages — so a default page of 25 cost
    ~75 sequential round trips. This does the same work in three queries total,
    regardless of page size, and returns the identical shape.
    """
    if not templates:
        return []

    template_ids = [t["id"] for t in templates]
    trade_ids = list({t["trade_id"] for t in templates if t.get("trade_id")})

    # 1. Trade names
    trade_names: dict[str, str] = {}
    if trade_ids:
        try:
            resp = db.table("trades").select("id, name").in_("id", trade_ids).execute()
            for row in (resp.data or []):
                trade_names[str(row["id"])] = row["name"]
        except APIError as exc:
            logger.warning("Failed to batch-fetch trade names: %s", exc)

    # 2. Item counts
    item_counts: dict[str, int] = {}
    try:
        resp = (
            db.table("bid_template_items")
            .select("bid_template_id")
            .in_("bid_template_id", template_ids)
            .execute()
        )
        for row in (resp.data or []):
            key = str(row["bid_template_id"])
            item_counts[key] = item_counts.get(key, 0) + 1
    except APIError as exc:
        logger.warning("Failed to batch-count template items: %s", exc)

    # 3. In-use flags. Same rule as _referencing_live_packages: any
    #    non-cancelled package locks the template.
    in_use: set[str] = set()
    try:
        resp = (
            db.table("bid_packages")
            .select("bid_template_id")
            .in_("bid_template_id", template_ids)
            .neq("status", "cancelled")
            .execute()
        )
        for row in (resp.data or []):
            if row.get("bid_template_id"):
                in_use.add(str(row["bid_template_id"]))
    except APIError as exc:
        logger.error("Failed to batch-check template usage: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to check template usage",
        ) from exc

    enriched = []
    for t in templates:
        tid = str(t["id"])
        enriched.append({
            **t,
            "trade_name": trade_names.get(str(t["trade_id"])) if t.get("trade_id") else None,
            "item_count": item_counts.get(tid, 0),
            "is_in_use": tid in in_use,
        })
    return enriched


def _build_detail_response(db: Client, template: dict) -> dict:
    """Enrich a template dict with trade_name, items, is_in_use, referencing_packages."""
    trade_name = None
    if template.get("trade_id"):
        try:
            trade_resp = (
                db.table("trades")
                .select("name")
                .eq("id", template["trade_id"])
                .maybe_single()
                .execute()
            )
            if trade_resp and trade_resp.data:
                trade_name = trade_resp.data["name"]
        except APIError as exc:
            logger.warning("Failed to fetch trade name for %s: %s", template["trade_id"], exc)

    try:
        items_resp = (
            db.table("bid_template_items")
            .select("*")
            .eq("bid_template_id", template["id"])
            .order("sort_order")
            .execute()
        )
        items = items_resp.data or []
    except APIError as exc:
        logger.warning("Failed to fetch items for template %s: %s", template["id"], exc)
        items = []

    live_pkgs = _referencing_live_packages(db, template["id"])

    return {
        **template,
        "trade_name": trade_name,
        "item_count": len(items),
        "items": items,
        "is_in_use": len(live_pkgs) > 0,
        # Cap the array; expose true total separately so the UI can render
        # "+N more" without us shipping potentially thousands of rows.
        "referencing_packages": live_pkgs[:_MAX_REFERENCING_PACKAGES],
        "referencing_packages_total": len(live_pkgs),
    }


def _validate_trade_id(db: Client, trade_id: UUID) -> None:
    """Verify trade_id references an existing, active trade.

    maybe_single() for the same reason as _get_template_or_404: with single(),
    a nonexistent trade raised APIError and was caught below as a 502, making
    the 422 beneath it unreachable — a PM picking a stale trade got a gateway
    error instead of a validation message.

    is_active is part of the check because trades are retired by flag, never
    deleted (schema: trades.is_active). Retired trades must not be selectable
    on new writes. This is a write-time gate only: templates already pointing
    at a since-retired trade keep working and still resolve their trade_name.
    """
    try:
        resp = (
            db.table("trades")
            .select("id")
            .eq("id", str(trade_id))
            .eq("is_active", True)
            .maybe_single()
            .execute()
        )
    except APIError as exc:
        logger.error("Failed to validate trade_id %s: %s", trade_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to validate trade",
        ) from exc

    if not resp or not resp.data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Trade not found or inactive",
        )


def _find_name_conflict(
    db: Client, name: str, *, exclude_id: UUID | str | None = None
) -> bool:
    """True if another template already uses this name.

    Case-insensitive and whitespace-insensitive, app-layer only (no DB unique
    constraint, by decision). Mirrors _company_name_exists in routers/vendors.py:
    narrow the fetch with ilike, then re-compare each candidate in Python, since
    a literal % or _ in the name would otherwise be read as an ilike wildcard.

    Scope is global rather than per-trade: the bid package wizard lists every
    template in one picker, which is exactly where two identical names hurt.

    exclude_id skips the row being updated, so re-saving a template without
    renaming it is not a conflict with itself.
    """
    target = name.strip().casefold()
    if not target:
        return False

    try:
        resp = (
            db.table("bid_templates")
            .select("id, name")
            .ilike("name", escape_like_pattern(name.strip()))
            .execute()
        )
    except APIError as exc:
        # Fail closed rather than silently allowing a duplicate through.
        logger.error("Failed to check bid template name uniqueness: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to verify template name availability",
        ) from exc

    exclude = str(exclude_id) if exclude_id is not None else None
    for row in (resp.data or []):
        if exclude is not None and str(row.get("id")) == exclude:
            continue
        if (row.get("name") or "").strip().casefold() == target:
            return True
    return False


def _reject_duplicate_name(
    db: Client, name: str, *, exclude_id: UUID | str | None = None
) -> None:
    if _find_name_conflict(db, name, exclude_id=exclude_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A bid template named '{name.strip()}' already exists.",
        )


#: Upper bound on the "Copy of X (n)" probe in the duplicate endpoint, so a
#: pathological name collision can't spin unbounded queries.
_MAX_COPY_NAME_ATTEMPTS = 50


def _available_copy_name(db: Client, source_name: str) -> str:
    """Pick a free name for a duplicate: 'Copy of X', then 'Copy of X (2)'...

    Duplicating twice collides by construction, and duplicate is the documented
    escape hatch for the freeze guard — it must not start returning 409s just
    because we added a name policy.
    """
    base = f"Copy of {source_name.strip()}"
    if not _find_name_conflict(db, base):
        return base

    for suffix in range(2, _MAX_COPY_NAME_ATTEMPTS + 1):
        candidate = f"{base} ({suffix})"
        if not _find_name_conflict(db, candidate):
            return candidate

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"Could not find an available name for a copy of '{source_name}'. "
            "Rename some existing copies and try again."
        ),
    )


def _insert_items(db: Client, template_id: str, items: list) -> None:
    """Bulk insert bid_template_items with sort_order based on position."""
    if not items:
        return
    rows = []
    for idx, item in enumerate(items):
        row = item.model_dump()
        row["bid_template_id"] = template_id
        row["sort_order"] = idx
        rows.append(row)
    try:
        db.table("bid_template_items").insert(rows).execute()
    except APIError as exc:
        logger.error("Failed to insert bid_template_items: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_DB_REJECTED_DETAIL,
        ) from exc


# ── Freeze-guard helpers (Task 8.1) ────────────────────────────────────


def _shape_package_summary(row: dict) -> dict:
    """Flatten the Supabase embedded `tasks(name)` payload into a flat summary."""
    task = row.get("tasks") or {}
    if isinstance(task, list):
        task = task[0] if task else {}
    return {
        "id": row["id"],
        "status": row["status"],
        "task_name": (task or {}).get("name", "Unknown task"),
    }


def _referencing_live_packages(db: Client, template_id) -> list[dict]:
    """Bid packages referencing this template whose status is NOT 'cancelled'.

    Each returned dict: {id, status, task_name}. A non-empty list means
    the template is locked: vendors are bidding against the current line
    items and changing them mid-round would break comparability.
    """
    try:
        resp = (
            db.table("bid_packages")
            .select("id, status, task_id, tasks(name)")
            .eq("bid_template_id", str(template_id))
            .neq("status", "cancelled")
            .execute()
        )
    except APIError as exc:
        logger.error("Failed to look up referencing bid_packages: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to check template usage",
        ) from exc

    return [_shape_package_summary(r) for r in (resp.data or [])]


def _is_template_in_use(db: Client, template_id) -> bool:
    return len(_referencing_live_packages(db, template_id)) > 0


def _all_referencing_packages(db: Client, template_id) -> list[dict]:
    """Every bid package referencing this template, including cancelled.

    Used by the DELETE 409 message: the FK RESTRICT blocks on *any*
    reference, so the message should list cancelled refs too.
    """
    try:
        resp = (
            db.table("bid_packages")
            .select("id, status, task_id, tasks(name)")
            .eq("bid_template_id", str(template_id))
            .execute()
        )
    except APIError as exc:
        logger.error("Failed to look up all referencing bid_packages: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to check template usage",
        ) from exc

    return [_shape_package_summary(r) for r in (resp.data or [])]


# Cap on how many referencing packages we surface to the user, both
# in 409 message bodies and in `BidTemplateDetailResponse.referencing_packages`.
# Anything past this collapses into a count (`+N more` / `referencing_packages_total`).
# Keeps the API + UI bounded when a template is heavily reused.
_MAX_REFERENCING_PACKAGES = 3


def _format_package_list(pkgs: list[dict]) -> str:
    """Render a human-readable '{task} ({status})' list for 409 messages."""
    if not pkgs:
        return ""
    visible = pkgs[:_MAX_REFERENCING_PACKAGES]
    rendered = ", ".join(f"{p['task_name']} ({p['status']})" for p in visible)
    remaining = len(pkgs) - len(visible)
    if remaining > 0:
        rendered += f", +{remaining} more"
    return rendered


# ── CRUD ────────────────────────────────────────────────────────────────


@router.get("/bid-templates", response_model=BidTemplateListResponse)
async def list_bid_templates(
    search: str | None = Query(default=None, description="Search by template name"),
    trade_id: str | None = Query(default=None, description="Filter by trade_id, or 'null' for general-purpose"),
    sort_by: str = Query(default="name", description="Column to sort by"),
    sort_dir: str = Query(default="asc", description="Sort direction: asc or desc"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=25, ge=1, le=100, description="Items per page"),
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """List all bid templates with search, trade filter, sort, and pagination."""

    # Validate trade_id format before sending to Postgres
    if trade_id and trade_id != "null":
        _parse_uuid(trade_id, "trade_id")

    query = db.table("bid_templates").select("*", count="exact")

    if search:
        query = query.ilike("name", f"%{escape_like_pattern(search)}%")

    if trade_id == "null":
        query = query.is_("trade_id", "null")
    elif trade_id:
        query = query.eq("trade_id", trade_id)

    # Sorting — whitelist to prevent injection
    allowed_sort_columns = {"name", "is_lump_sum", "created_at", "updated_at"}
    if sort_by not in allowed_sort_columns:
        sort_by = "name"
    ascending = sort_dir.lower() != "desc"
    query = query.order(sort_by, desc=not ascending)

    # Pagination
    offset = (page - 1) * page_size
    query = query.range(offset, offset + page_size - 1)

    try:
        response = query.execute()
    except APIError as exc:
        logger.error("Supabase query failed for bid_templates list: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch bid templates from database",
        ) from exc

    templates = response.data or []

    # Enrich the whole page in three queries rather than three per row.
    enriched = _enrich_templates_batched(db, templates)

    return BidTemplateListResponse(
        items=enriched,
        total=response.count or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/bid-templates/{template_id}", response_model=BidTemplateDetailResponse)
async def get_bid_template(
    template_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Get a single bid template with all its items."""
    template = _get_template_or_404(db, template_id)
    return _build_detail_response(db, template)


@router.post(
    "/bid-templates",
    response_model=BidTemplateDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bid_template(
    body: BidTemplateCreate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Create a new bid template with inline items."""

    _reject_duplicate_name(db, body.name)

    # Validate trade_id if provided
    if body.trade_id:
        _validate_trade_id(db, body.trade_id)

    # Build template data
    template_data = body.model_dump(exclude={"items"})
    template_data["created_by"] = user["user_id"]
    if template_data.get("trade_id"):
        template_data["trade_id"] = str(template_data["trade_id"])

    try:
        resp = db.table("bid_templates").insert(template_data).execute()
    except APIError as exc:
        logger.error("Supabase insert failed for bid_templates: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_DB_REJECTED_DETAIL,
        ) from exc

    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create bid template",
        )

    new_template = resp.data[0]

    # Insert items
    _insert_items(db, new_template["id"], body.items)

    return _build_detail_response(db, new_template)


@router.put("/bid-templates/{template_id}", response_model=BidTemplateDetailResponse)
async def update_bid_template(
    template_id: UUID,
    body: BidTemplateUpdate,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Update a bid template's metadata and replace all items.

    Blocked with 409 when the template is referenced by any non-cancelled
    bid_package: the items vendors are bidding against must stay frozen
    for the duration of the round (Task 8.1). The check runs *before*
    any write so a rejected PUT leaves bid_template_items untouched.
    Escape hatch: POST /bid-templates/{id}/duplicate.
    """

    _get_template_or_404(db, template_id)

    live_pkgs = _referencing_live_packages(db, template_id)
    if live_pkgs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This template is in use by a live bid package "
                f"({_format_package_list(live_pkgs)}) and is locked to "
                "keep all vendor bids comparable. Duplicate it to make changes."
            ),
        )

    # Exclude self: re-saving a template without renaming it is not a
    # conflict with its own row.
    _reject_duplicate_name(db, body.name, exclude_id=template_id)

    # Validate trade_id if provided
    if body.trade_id:
        _validate_trade_id(db, body.trade_id)

    # Update metadata
    update_data = body.model_dump(exclude={"items"})
    if update_data.get("trade_id"):
        update_data["trade_id"] = str(update_data["trade_id"])

    try:
        db.table("bid_templates").update(update_data).eq("id", str(template_id)).execute()
    except APIError as exc:
        logger.error("Supabase update failed for bid_templates: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_DB_REJECTED_DETAIL,
        ) from exc

    # Replace items: delete all existing, insert new
    try:
        db.table("bid_template_items").delete().eq(
            "bid_template_id", str(template_id)
        ).execute()
    except APIError as exc:
        logger.error("Failed to delete old items for template %s: %s", template_id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to replace template items",
        ) from exc

    _insert_items(db, str(template_id), body.items)

    # Fetch updated template for response
    updated = _get_template_or_404(db, template_id)
    return _build_detail_response(db, updated)


@router.delete("/bid-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bid_template(
    template_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Delete a bid template.

    The FK `bid_packages.bid_template_id` ON DELETE RESTRICT blocks the
    delete whenever *any* package (including cancelled) references it.
    We pre-check so the 409 can name the blocking package(s) and status.
    The bare "in use" message left PMs guessing (Task 8.1).
    """

    _get_template_or_404(db, template_id)

    all_pkgs = _all_referencing_packages(db, template_id)
    if all_pkgs:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This template is referenced by bid package(s) "
                f"({_format_package_list(all_pkgs)}) and cannot be deleted."
            ),
        )

    try:
        db.table("bid_templates").delete().eq("id", str(template_id)).execute()
    except APIError as exc:
        # Defense in depth: race between pre-check and delete could surface
        # the original FK error. Re-raise with the same enriched message.
        if "23503" in str(exc.code) or "violates foreign key" in str(exc.message).lower():
            racing_pkgs = _all_referencing_packages(db, template_id)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This template is referenced by bid package(s) "
                    f"({_format_package_list(racing_pkgs)}) and cannot be deleted."
                ),
            ) from exc
        logger.error("Supabase delete failed for bid_templates: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_DB_REJECTED_DETAIL,
        ) from exc


@router.post(
    "/bid-templates/{template_id}/duplicate",
    response_model=BidTemplateDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_bid_template(
    template_id: UUID,
    user: dict = Depends(get_current_active_user),
    db: Client = Depends(get_supabase),
):
    """Deep-copy a bid template and its items into a new template.

    This is the escape hatch for the edit-guard freeze (Task 8.1): when a
    template is locked because a live package references it, the PM
    duplicates it, edits the copy, and points the *next* round at it.
    Duplicating an editable template is fine too: no in-use check here.
    """

    source = _get_template_or_404(db, template_id)

    new_template_data = {
        "name": _available_copy_name(db, source["name"]),
        "trade_id": source.get("trade_id"),
        "is_lump_sum": source.get("is_lump_sum", True),
        "created_by": user["user_id"],
    }

    try:
        resp = db.table("bid_templates").insert(new_template_data).execute()
    except APIError as exc:
        logger.error("Supabase insert failed duplicating bid_template: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_DB_REJECTED_DETAIL,
        ) from exc

    if not resp.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to duplicate bid template",
        )

    new_template = resp.data[0]

    # Copy items in sort_order. We DON'T reuse `_insert_items` because that
    # helper consumes Pydantic models and re-derives sort_order from list
    # position; here we already have raw dicts and want to preserve the
    # source ordering verbatim (and skip `id`/`bid_template_id` fields).
    try:
        items_resp = (
            db.table("bid_template_items")
            .select("description, item_type, unit_of_measure, sort_order")
            .eq("bid_template_id", str(template_id))
            .order("sort_order")
            .execute()
        )
        source_items = items_resp.data or []
    except APIError as exc:
        logger.error("Failed to read source items during duplicate: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to read source template items",
        ) from exc

    if source_items:
        copy_rows = [
            {
                "bid_template_id": new_template["id"],
                "description": row["description"],
                "item_type": row["item_type"],
                "unit_of_measure": row.get("unit_of_measure"),
                "sort_order": row["sort_order"],
            }
            for row in source_items
        ]
        try:
            db.table("bid_template_items").insert(copy_rows).execute()
        except APIError as exc:
            logger.error("Failed to insert duplicated items: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_DB_REJECTED_DETAIL,
            ) from exc

    return _build_detail_response(db, new_template)
