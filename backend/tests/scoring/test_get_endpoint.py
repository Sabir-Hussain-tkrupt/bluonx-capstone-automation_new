"""HTTP-level tests for GET /api/v1/bid-packages/{id}/scores (Task 8.3/8.4 seam).

Read-only enriched endpoint: persisted bid_scores joined to the LIVE
non-superseded cohort, enriched with vendor_company_name on each row and
budget_estimate on the envelope. Empty/never-computed returns 200 with
scores:[] (not 404); 404 for unknown package; 400 for non-competitive.
"""

from __future__ import annotations

from datetime import datetime

from .conftest import (
    BID_PACKAGE_ID,
    INVITATION_IDS,
    SCORE_ROW_IDS,
    SUBMISSION_IDS,
    UNKNOWN_BID_PACKAGE_ID,
    VENDOR_IDS,
    make_invitation,
    make_score_row,
    make_submission,
)


URL_TPL = "/api/v1/bid-packages/{pkg}/scores"

COMPANY_NAMES = ["Acme Co.", "Beta LLC", "Gamma Inc."]
SUBMITTED_AT_VALUES = [
    "2026-06-25T10:00:00+00:00",
    "2026-06-29T14:30:00+00:00",   # max
    "2026-06-27T08:15:00+00:00",
]


def _package_with_budget(
    *, bid_type: str = "competitive", budget: str | None = "500000.00"
) -> dict:
    """Mirrors what the GET service requests: `id, tasks!inner(bid_type, budget_estimate)`."""
    return {
        "id": str(BID_PACKAGE_ID),
        "tasks": {"bid_type": bid_type, "budget_estimate": budget},
    }


def _with_enrichment(
    sub: dict, score: dict | None, company_name: str, submitted_at: str
) -> dict:
    """Embed a vendors row and a bid_scores relation on the submission."""
    return {
        **sub,
        "submitted_at": submitted_at,
        "vendors": {"company_name": company_name},
        "bid_scores": [score] if score else [],
    }


def _happy_spec() -> dict:
    """Three submissions; each has a persisted score row and a vendor name."""
    raw_subs = [
        make_submission(
            submission_id=SUBMISSION_IDS[i],
            vendor_id=VENDOR_IDS[i],
            bid_invitation_id=INVITATION_IDS[i],
            total_amount=str(80000 + 10000 * i) + ".00",
        )
        for i in range(3)
    ]
    scored_subs = [
        _with_enrichment(
            raw_subs[i],
            make_score_row(score_id=SCORE_ROW_IDS[i], submission_id=SUBMISSION_IDS[i]),
            COMPANY_NAMES[i],
            SUBMITTED_AT_VALUES[i],
        )
        for i in range(3)
    ]
    invitations = [make_invitation(invitation_id=INVITATION_IDS[i]) for i in range(3)]
    return {
        "bid_packages": {"select": _package_with_budget()},
        "bid_invitations": {"select": invitations},
        "bid_submissions": {"select": scored_subs},
    }


# ── 1. Happy path ────────────────────────────────────────────────────────


def test_happy_path_returns_200_with_enriched_cohort(client_factory):
    client, db = client_factory(_happy_spec())
    r = client.get(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["bid_package_id"] == str(BID_PACKAGE_ID)
    assert body["rubric_version"] == "v1.0"
    assert body["cohort_size"] == 3
    assert body["valid_submission_count"] == 3
    assert body["budget_estimate"] == "500000.00"
    # Pydantic may normalize the offset form (e.g. "+00:00" → "Z"); compare
    # semantically, not by string.
    assert datetime.fromisoformat(
        body["latest_submission_at"].replace("Z", "+00:00")
    ) == datetime.fromisoformat("2026-06-29T14:30:00+00:00")

    assert isinstance(body["scores"], list)
    assert len(body["scores"]) == 3
    for row in body["scores"]:
        assert "vendor_company_name" in row
        assert row["vendor_company_name"] in COMPANY_NAMES
        for field in (
            "id", "bid_submission_id", "price_score", "compliance_score",
            "performance_score", "capacity_score", "timeline_score",
            "total_weighted_score", "scoring_metadata", "scored_at",
        ):
            assert field in row

    # Task 8.4: recommendation envelope is populated by GET (POST leaves None).
    rec = body["recommendation"]
    assert rec is not None
    assert rec["recommended_bid_submission_id"] == rec["ranking"][0]["bid_submission_id"]
    assert len(rec["ranking"]) == 3
    assert [r["rank"] for r in rec["ranking"]] == [1, 2, 3]
    assert isinstance(rec["justification"], str) and rec["justification"]


# ── 2. Live-cohort filter — superseded gate is present in the query ──────


def test_query_filters_to_live_non_superseded_cohort(client_factory):
    """The cohort query MUST carry is_superseded=False, is_draft=False, and a
    status IN ('submitted','under_review') filter so that stale score rows for
    now-superseded submissions can never leak through the join. Inspecting the
    chain mock's filter-method call_args (the mock only logs the five terminal
    ops in _call_log, not filter calls)."""
    client, db = client_factory(_happy_spec())
    r = client.get(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 200, r.text

    sub_chain = db._chains["bid_submissions"]
    eq_calls = [tuple(c.args) for c in sub_chain.eq.call_args_list]
    in_calls = [tuple(c.args) for c in sub_chain.in_.call_args_list]

    assert ("is_superseded", False) in eq_calls, (
        f"Missing is_superseded=False on cohort query. eq() calls: {eq_calls}"
    )
    assert ("is_draft", False) in eq_calls, (
        f"Missing is_draft=False on cohort query. eq() calls: {eq_calls}"
    )

    status_filters = [a for a in in_calls if a and a[0] == "status"]
    assert status_filters, (
        f"Missing status IN COHORT_STATUSES on cohort query. in_() calls: {in_calls}"
    )
    statuses = set(status_filters[0][1])
    assert {"submitted", "under_review"}.issubset(statuses)


# ── 3. Never-computed → 200 with scores:[] (not 404) ─────────────────────


def test_never_computed_returns_200_empty_scores_with_live_count(client_factory):
    """Submissions exist but no bid_scores rows persisted yet."""
    raw_subs = [
        make_submission(
            submission_id=SUBMISSION_IDS[i],
            vendor_id=VENDOR_IDS[i],
            bid_invitation_id=INVITATION_IDS[i],
            total_amount=str(80000 + 10000 * i) + ".00",
        )
        for i in range(3)
    ]
    unscored = [
        _with_enrichment(raw_subs[i], None, COMPANY_NAMES[i], SUBMITTED_AT_VALUES[i])
        for i in range(3)
    ]
    spec = {
        "bid_packages": {"select": _package_with_budget()},
        "bid_invitations": {
            "select": [make_invitation(invitation_id=INVITATION_IDS[i]) for i in range(3)]
        },
        "bid_submissions": {"select": unscored},
    }
    client, _ = client_factory(spec)
    r = client.get(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scores"] == []
    assert body["cohort_size"] == 0
    assert body["valid_submission_count"] == 3
    assert body["budget_estimate"] == "500000.00"
    assert body["rubric_version"] == "v1.0"
    # Task 8.4: empty cohort → recommendation is null (frontend renders CTA).
    assert body["recommendation"] is None


# ── 4. No invitations → 200 empty (NOT 422) ──────────────────────────────


def test_no_invitations_returns_200_empty(client_factory):
    spec = {
        "bid_packages": {"select": _package_with_budget()},
        "bid_invitations": {"select": []},
        "bid_submissions": {"select": []},
    }
    client, _ = client_factory(spec)
    r = client.get(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scores"] == []
    assert body["cohort_size"] == 0
    assert body["valid_submission_count"] == 0
    assert body["latest_submission_at"] is None


# ── 5. 404 unknown package ───────────────────────────────────────────────


def test_unknown_package_returns_404(client_factory):
    client, _ = client_factory({"bid_packages": {"select": None}})
    r = client.get(URL_TPL.format(pkg=UNKNOWN_BID_PACKAGE_ID))
    assert r.status_code == 404


# ── 6. 400 non-competitive — direct_assign ───────────────────────────────


def test_direct_assign_package_returns_400(client_factory):
    spec = _happy_spec()
    spec["bid_packages"] = {"select": _package_with_budget(bid_type="direct_assign")}
    client, _ = client_factory(spec)
    r = client.get(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 400


# ── 7. 400 non-competitive — internal ────────────────────────────────────


def test_internal_package_returns_400(client_factory):
    spec = _happy_spec()
    spec["bid_packages"] = {"select": _package_with_budget(bid_type="internal")}
    client, _ = client_factory(spec)
    r = client.get(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 400


# ── 8. NULL budget_estimate passes through ───────────────────────────────


def test_null_budget_estimate_passes_through_as_null(client_factory):
    spec = _happy_spec()
    spec["bid_packages"] = {"select": _package_with_budget(budget=None)}
    client, _ = client_factory(spec)
    r = client.get(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["budget_estimate"] is None
    assert body["cohort_size"] == 3


# ── 9. Invalid total_amount excluded from valid_submission_count ─────────


def test_invalid_totals_excluded_from_valid_submission_count(client_factory):
    """One valid total, one None total, one zero total → valid_submission_count == 1.
    Mirrors POST's cohort rule (total_amount > 0)."""
    valid_sub = _with_enrichment(
        make_submission(
            submission_id=SUBMISSION_IDS[0],
            vendor_id=VENDOR_IDS[0],
            bid_invitation_id=INVITATION_IDS[0],
            total_amount="90000.00",
        ),
        make_score_row(score_id=SCORE_ROW_IDS[0], submission_id=SUBMISSION_IDS[0]),
        COMPANY_NAMES[0],
        SUBMITTED_AT_VALUES[0],
    )
    null_total_sub = _with_enrichment(
        make_submission(
            submission_id=SUBMISSION_IDS[1],
            vendor_id=VENDOR_IDS[1],
            bid_invitation_id=INVITATION_IDS[1],
            total_amount=None,
        ),
        None,
        COMPANY_NAMES[1],
        SUBMITTED_AT_VALUES[1],
    )
    zero_total_sub = _with_enrichment(
        make_submission(
            submission_id=SUBMISSION_IDS[2],
            vendor_id=VENDOR_IDS[2],
            bid_invitation_id=INVITATION_IDS[2],
            total_amount="0",
        ),
        None,
        COMPANY_NAMES[2],
        SUBMITTED_AT_VALUES[2],
    )
    spec = {
        "bid_packages": {"select": _package_with_budget()},
        "bid_invitations": {
            "select": [make_invitation(invitation_id=INVITATION_IDS[i]) for i in range(3)]
        },
        "bid_submissions": {"select": [valid_sub, null_total_sub, zero_total_sub]},
    }
    client, _ = client_factory(spec)
    r = client.get(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid_submission_count"] == 1
    assert body["cohort_size"] == 1
    assert body["scores"][0]["vendor_company_name"] == COMPANY_NAMES[0]


# ── 10. Read does NOT write — no mutating ops on bid_scores ──────────────


def test_read_endpoint_performs_no_writes(client_factory):
    client, db = client_factory(_happy_spec())
    r = client.get(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 200, r.text

    bid_scores_ops = [c[1] for c in db._call_log if c[0] == "bid_scores"]
    forbidden = {"insert", "update", "upsert", "delete"}
    bad = [op for op in bid_scores_ops if op in forbidden]
    assert not bad, (
        f"GET /scores must not mutate bid_scores. Saw ops: {bid_scores_ops}"
    )
