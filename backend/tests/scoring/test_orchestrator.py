"""Orchestrator tests for `score_bid_package` (Task 8.2).

Asserts:
  - competitive-only gate (400 on direct_assign / internal)
  - 404 on unknown package
  - cohort filtering (drafts / superseded / wrong status / null total / zero total)
  - 422 when cohort is empty
  - weight math rounded to 2 dp
  - upsert idempotency (manual rows preserved; system rows recomputed)
  - scoring_metadata snapshot contents (including `basis: no_desired_date`)
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.bid_scoring_service import (
    NEUTRAL_CAPACITY_SCORE,
    NEUTRAL_PERFORMANCE_SCORE,
    RUBRIC_VERSION,
    WEIGHTS,
    BidScoringError,
    score_bid_package,
)

from .conftest import (
    BID_PACKAGE_ID,
    INVITATION_IDS,
    PM_USER_ID,
    SCORE_ROW_IDS,
    SUBMISSION_IDS,
    UNKNOWN_BID_PACKAGE_ID,
    VENDOR_IDS,
    make_db,
    make_invitation,
    make_package,
    make_score_row,
    make_submission,
    make_vendor,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _build_default_cohort_spec(
    *,
    package_overrides: dict | None = None,
    submissions: list[dict] | None = None,
    invitations: list[dict] | None = None,
    existing_scores: list[dict] | None = None,
    upsert_returns: list[dict] | None = None,
) -> dict:
    """Compose a make_db spec for a happy 3-vendor cohort."""
    pkg = make_package(**(package_overrides or {}))

    if submissions is None:
        submissions = [
            make_submission(
                submission_id=SUBMISSION_IDS[i],
                vendor_id=VENDOR_IDS[i],
                bid_invitation_id=INVITATION_IDS[i],
                total_amount=str(80000 + 10000 * i) + ".00",
            )
            for i in range(3)
        ]
    if invitations is None:
        invitations = [
            make_invitation(invitation_id=INVITATION_IDS[i])
            for i in range(3)
        ]
    if existing_scores is None:
        existing_scores = []
    if upsert_returns is None:
        upsert_returns = [
            make_score_row(
                score_id=SCORE_ROW_IDS[i], submission_id=SUBMISSION_IDS[i]
            )
            for i in range(len(submissions))
        ]

    return {
        "bid_packages": {"select": pkg},
        "bid_invitations": {"select": invitations},
        "bid_submissions": {"select": submissions},
        "bid_scores": {
            "select": existing_scores,
            "upsert": upsert_returns,
        },
    }


# ── 404 / 400 gates ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_package_raises_404():
    db = make_db({"bid_packages": {"select": None}})
    with pytest.raises(BidScoringError) as exc:
        await score_bid_package(
            UNKNOWN_BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_unknown_package_empty_list_raises_404():
    db = make_db({"bid_packages": {"select": []}})
    with pytest.raises(BidScoringError) as exc:
        await score_bid_package(
            UNKNOWN_BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_direct_assign_task_raises_400():
    spec = _build_default_cohort_spec(
        package_overrides={"bid_type": "direct_assign"}
    )
    db = make_db(spec)
    with pytest.raises(BidScoringError) as exc:
        await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_internal_task_raises_400():
    spec = _build_default_cohort_spec(
        package_overrides={"bid_type": "internal"}
    )
    db = make_db(spec)
    with pytest.raises(BidScoringError) as exc:
        await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)
    assert exc.value.status_code == 400


# ── Cohort filtering / 422 ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_invitations_raises_422():
    spec = _build_default_cohort_spec(invitations=[])
    db = make_db(spec)
    with pytest.raises(BidScoringError) as exc:
        await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_no_submissions_raises_422():
    spec = _build_default_cohort_spec(submissions=[])
    db = make_db(spec)
    with pytest.raises(BidScoringError) as exc:
        await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_all_null_totals_raises_422():
    subs = [
        make_submission(
            submission_id=SUBMISSION_IDS[i],
            vendor_id=VENDOR_IDS[i],
            bid_invitation_id=INVITATION_IDS[i],
            total_amount=None,
        )
        for i in range(3)
    ]
    spec = _build_default_cohort_spec(submissions=subs)
    db = make_db(spec)
    with pytest.raises(BidScoringError) as exc:
        await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_all_zero_totals_raises_422():
    subs = [
        make_submission(
            submission_id=SUBMISSION_IDS[i],
            vendor_id=VENDOR_IDS[i],
            bid_invitation_id=INVITATION_IDS[i],
            total_amount="0",
        )
        for i in range(3)
    ]
    spec = _build_default_cohort_spec(submissions=subs)
    db = make_db(spec)
    with pytest.raises(BidScoringError) as exc:
        await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_filters_null_and_zero_totals_keeps_valid():
    """One valid submission survives a cohort with garbage entries."""
    subs = [
        make_submission(
            submission_id=SUBMISSION_IDS[0], vendor_id=VENDOR_IDS[0],
            bid_invitation_id=INVITATION_IDS[0], total_amount="100000.00",
        ),
        make_submission(
            submission_id=SUBMISSION_IDS[1], vendor_id=VENDOR_IDS[1],
            bid_invitation_id=INVITATION_IDS[1], total_amount=None,
        ),
        make_submission(
            submission_id=SUBMISSION_IDS[2], vendor_id=VENDOR_IDS[2],
            bid_invitation_id=INVITATION_IDS[2], total_amount="0.00",
        ),
    ]
    upsert_returns = [
        make_score_row(score_id=SCORE_ROW_IDS[0], submission_id=SUBMISSION_IDS[0])
    ]
    spec = _build_default_cohort_spec(
        submissions=subs, upsert_returns=upsert_returns
    )
    db = make_db(spec)

    result = await score_bid_package(
        BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db
    )
    assert result["cohort_size"] == 1


# ── Weight math + metadata ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_weight_math_rounded_to_two_decimals():
    """
    Three-vendor cohort: bids $80k / $90k / $100k.
      lowest = 80000
      vendor[0]: price=100, compliance=100, perf=75, capacity=80, timeline=100
        total = 0.5*100 + 0.05*100 + 0.20*75 + 0.10*80 + 0.15*100
              = 50 + 5 + 15 + 8 + 15 = 93.00
      vendor[1]: price = 80/90*100 = 88.888... → 0.5*88.888 = 44.4444...
        contributes round to 2dp at the very end → total ~ 87.44 (or so).
    Pin vendor[0] precisely; sanity-check vendor[1] is rounded to 2dp.
    """
    vendor_full_capacity = make_vendor(max_active_jobs=10, current_active_jobs=2)
    # vendor[0]: capacity = (10-2)/10 = 80
    subs = [
        make_submission(
            submission_id=SUBMISSION_IDS[i],
            vendor_id=VENDOR_IDS[i],
            bid_invitation_id=INVITATION_IDS[i],
            total_amount=str(80000 + 10000 * i) + ".00",
            proposed_start_date=None,  # not used: desired present, so guard...
            vendor=vendor_full_capacity,
        )
        for i in range(3)
    ]
    # set proposed = desired (on time → 100)
    from datetime import date
    for s in subs:
        s["proposed_start_date"] = date(2026, 7, 15).isoformat()

    upsert_returns = [
        make_score_row(score_id=SCORE_ROW_IDS[i], submission_id=SUBMISSION_IDS[i])
        for i in range(3)
    ]
    spec = _build_default_cohort_spec(
        submissions=subs, upsert_returns=upsert_returns
    )
    db = make_db(spec)

    await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)

    # Inspect the upsert payload to assert weight math precisely.
    upsert_calls = [
        c for c in db._call_log if c[0] == "bid_scores" and c[1] == "upsert"
    ]
    assert len(upsert_calls) == 1
    rows = upsert_calls[0][2][0]   # first positional arg to .upsert()
    assert len(rows) == 3

    by_sub = {r["bid_submission_id"]: r for r in rows}

    # Vendor 0 — lowest bid, full perf/capacity/timeline
    v0 = by_sub[str(SUBMISSION_IDS[0])]
    assert Decimal(v0["price_score"]) == Decimal("100.00")
    assert Decimal(v0["capacity_score"]) == Decimal("80.00")
    assert Decimal(v0["performance_score"]) == Decimal(str(NEUTRAL_PERFORMANCE_SCORE))
    assert Decimal(v0["timeline_score"]) == Decimal("100.00")
    assert Decimal(v0["total_weighted_score"]) == Decimal("93.00")

    # Vendor 1 — price 80/90 * 100 → ~88.888
    v1 = by_sub[str(SUBMISSION_IDS[1])]
    p1 = Decimal(v1["price_score"])
    expected_total = round(
        WEIGHTS["price"] * float(p1)
        + WEIGHTS["compliance"] * 100.0
        + WEIGHTS["performance"] * NEUTRAL_PERFORMANCE_SCORE
        + WEIGHTS["capacity"] * 80.0
        + WEIGHTS["timeline"] * 100.0,
        2,
    )
    assert Decimal(v1["total_weighted_score"]) == Decimal(str(expected_total))


@pytest.mark.asyncio
async def test_metadata_snapshot_contents():
    spec = _build_default_cohort_spec()
    db = make_db(spec)
    await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)

    upsert_calls = [
        c for c in db._call_log if c[0] == "bid_scores" and c[1] == "upsert"
    ]
    rows = upsert_calls[0][2][0]
    meta = rows[0]["scoring_metadata"]

    assert meta["rubric_version"] == RUBRIC_VERSION
    assert meta["weights"] == WEIGHTS
    assert "inputs" in meta and isinstance(meta["inputs"], dict)
    assert "sub_scores" in meta and set(meta["sub_scores"].keys()) == {
        "price", "compliance", "performance", "capacity", "timeline"
    }
    assert meta["cohort_size"] == 3
    assert "computed_at" in meta
    # desired_start_date is present on the default package, so basis absent.
    assert meta.get("basis") != "no_desired_date"


@pytest.mark.asyncio
async def test_metadata_basis_no_desired_date_when_package_has_none():
    spec = _build_default_cohort_spec(
        package_overrides={"desired_start_date": None}
    )
    db = make_db(spec)
    await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)

    upsert_calls = [
        c for c in db._call_log if c[0] == "bid_scores" and c[1] == "upsert"
    ]
    rows = upsert_calls[0][2][0]
    for row in rows:
        assert row["scoring_metadata"]["basis"] == "no_desired_date"
        # All timeline scores should be 100 (cohort constant) per spec.
        assert Decimal(row["timeline_score"]) == Decimal("100.00")


# ── Manual-row preservation seam ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_adjusted_row_is_preserved():
    manual_row = make_score_row(
        score_id=SCORE_ROW_IDS[1],
        submission_id=SUBMISSION_IDS[1],
        scored_by=PM_USER_ID,                      # ← manual
        total_weighted_score="42.00",
        scoring_metadata={"rubric_version": "manual"},
    )
    spec = _build_default_cohort_spec(
        existing_scores=[manual_row],
        upsert_returns=[
            make_score_row(
                score_id=SCORE_ROW_IDS[0], submission_id=SUBMISSION_IDS[0]
            ),
            make_score_row(
                score_id=SCORE_ROW_IDS[2], submission_id=SUBMISSION_IDS[2]
            ),
        ],
    )
    db = make_db(spec)

    result = await score_bid_package(
        BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db
    )

    # Cohort size is still 3 — manual row is part of the result, just not upserted.
    assert result["cohort_size"] == 3

    upsert_calls = [
        c for c in db._call_log if c[0] == "bid_scores" and c[1] == "upsert"
    ]
    rows_sent = upsert_calls[0][2][0]
    sent_ids = {r["bid_submission_id"] for r in rows_sent}
    assert str(SUBMISSION_IDS[1]) not in sent_ids
    assert sent_ids == {str(SUBMISSION_IDS[0]), str(SUBMISSION_IDS[2])}

    # Manual row appears in the response untouched.
    returned_ids = {r["bid_submission_id"] for r in result["scores"]}
    assert str(SUBMISSION_IDS[1]) in returned_ids
    manual = next(
        r for r in result["scores"]
        if r["bid_submission_id"] == str(SUBMISSION_IDS[1])
    )
    assert manual["total_weighted_score"] == "42.00"
    assert manual["scored_by"] == str(PM_USER_ID)


@pytest.mark.asyncio
async def test_system_row_is_overwritten_on_recompute():
    system_row = make_score_row(
        score_id=SCORE_ROW_IDS[0],
        submission_id=SUBMISSION_IDS[0],
        scored_by=None,                            # ← system
        total_weighted_score="11.11",
    )
    spec = _build_default_cohort_spec(existing_scores=[system_row])
    db = make_db(spec)

    await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)

    upsert_calls = [
        c for c in db._call_log if c[0] == "bid_scores" and c[1] == "upsert"
    ]
    rows_sent = upsert_calls[0][2][0]
    sent_ids = {r["bid_submission_id"] for r in rows_sent}
    # System-scored row IS included in upsert (gets recomputed)
    assert str(SUBMISSION_IDS[0]) in sent_ids


@pytest.mark.asyncio
async def test_upsert_uses_bid_submission_id_conflict_target():
    spec = _build_default_cohort_spec()
    db = make_db(spec)
    await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)

    upsert_calls = [
        c for c in db._call_log if c[0] == "bid_scores" and c[1] == "upsert"
    ]
    assert len(upsert_calls) == 1
    _, _, args, kwargs = upsert_calls[0]
    # Either via kwarg on_conflict= or positional — accept either; the
    # value must be "bid_submission_id" so the partial unique index is hit.
    assert kwargs.get("on_conflict") == "bid_submission_id"


@pytest.mark.asyncio
async def test_recompute_idempotent():
    """Running the orchestrator twice in a row yields identical upsert payloads."""
    spec = _build_default_cohort_spec()
    db = make_db(spec)

    await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)
    first_call = [
        c for c in db._call_log if c[0] == "bid_scores" and c[1] == "upsert"
    ][0]
    first_rows = first_call[2][0]

    # Reset call log (but reuse same mocked data) to capture the second run.
    db._call_log.clear()
    await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)
    second_call = [
        c for c in db._call_log if c[0] == "bid_scores" and c[1] == "upsert"
    ][0]
    second_rows = second_call[2][0]

    # Compare deterministic fields (ignore `computed_at` and `scored_at`).
    def _stable(row):
        meta = {k: v for k, v in row["scoring_metadata"].items() if k != "computed_at"}
        return {**{k: v for k, v in row.items() if k not in ("scored_at", "scoring_metadata")}, "scoring_metadata": meta}

    assert [_stable(r) for r in first_rows] == [_stable(r) for r in second_rows]


# ── Cohort status / draft / superseded filtering ─────────────────────────


@pytest.mark.asyncio
async def test_cohort_query_filters_drafts_and_superseded_and_status():
    """Verify the orchestrator delegates draft/superseded/status filtering to PostgREST."""
    spec = _build_default_cohort_spec()
    db = make_db(spec)
    await score_bid_package(BID_PACKAGE_ID, scored_by=PM_USER_ID, db=db)

    sub_chain = db._chains["bid_submissions"]
    eq_calls = [c.args for c in sub_chain.eq.call_args_list]
    in_calls = [c.args for c in sub_chain.in_.call_args_list]

    assert ("is_draft", False) in eq_calls
    assert ("is_superseded", False) in eq_calls

    status_in_call = next(
        (args for args in in_calls if args and args[0] == "status"), None
    )
    assert status_in_call is not None
    assert set(status_in_call[1]) == {"submitted", "under_review"}
