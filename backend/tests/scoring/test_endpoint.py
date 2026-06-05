"""HTTP-level tests for POST /api/v1/bid-packages/{id}/scores (Task 8.2)."""

from __future__ import annotations

from .conftest import (
    BID_PACKAGE_ID,
    INVITATION_IDS,
    SCORE_ROW_IDS,
    SUBMISSION_IDS,
    UNKNOWN_BID_PACKAGE_ID,
    VENDOR_IDS,
    make_invitation,
    make_package,
    make_score_row,
    make_submission,
)


URL_TPL = "/api/v1/bid-packages/{pkg}/scores"


def _happy_spec() -> dict:
    submissions = [
        make_submission(
            submission_id=SUBMISSION_IDS[i],
            vendor_id=VENDOR_IDS[i],
            bid_invitation_id=INVITATION_IDS[i],
            total_amount=str(80000 + 10000 * i) + ".00",
        )
        for i in range(3)
    ]
    invitations = [
        make_invitation(invitation_id=INVITATION_IDS[i]) for i in range(3)
    ]
    upsert_returns = [
        make_score_row(score_id=SCORE_ROW_IDS[i], submission_id=SUBMISSION_IDS[i])
        for i in range(3)
    ]
    return {
        "bid_packages": {"select": make_package()},
        "bid_invitations": {"select": invitations},
        "bid_submissions": {"select": submissions},
        "bid_scores": {"select": [], "upsert": upsert_returns},
    }


def test_happy_path_returns_200_with_cohort_shape(client_factory):
    client, _ = client_factory(_happy_spec())
    r = client.post(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bid_package_id"] == str(BID_PACKAGE_ID)
    assert body["rubric_version"] == "v1.0"
    assert body["cohort_size"] == 3
    assert isinstance(body["scores"], list)
    assert len(body["scores"]) == 3
    # Spot-check that one returned row carries the expected fields.
    row = body["scores"][0]
    for field in (
        "id", "bid_submission_id", "price_score", "compliance_score",
        "performance_score", "capacity_score", "timeline_score",
        "total_weighted_score", "scoring_metadata",
    ):
        assert field in row


def test_unknown_bid_package_returns_404(client_factory):
    spec = {"bid_packages": {"select": None}}
    client, _ = client_factory(spec)
    r = client.post(URL_TPL.format(pkg=UNKNOWN_BID_PACKAGE_ID))
    assert r.status_code == 404


def test_non_competitive_package_returns_400(client_factory):
    spec = _happy_spec()
    spec["bid_packages"] = {"select": make_package(bid_type="direct_assign")}
    client, _ = client_factory(spec)
    r = client.post(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 400


def test_internal_package_returns_400(client_factory):
    spec = _happy_spec()
    spec["bid_packages"] = {"select": make_package(bid_type="internal")}
    client, _ = client_factory(spec)
    r = client.post(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 400


def test_no_valid_submissions_returns_422(client_factory):
    spec = _happy_spec()
    # Replace all submissions with null totals so the cohort drops to empty.
    nulls = [
        make_submission(
            submission_id=SUBMISSION_IDS[i],
            vendor_id=VENDOR_IDS[i],
            bid_invitation_id=INVITATION_IDS[i],
            total_amount=None,
        )
        for i in range(3)
    ]
    spec["bid_submissions"] = {"select": nulls}
    client, _ = client_factory(spec)
    r = client.post(URL_TPL.format(pkg=BID_PACKAGE_ID))
    assert r.status_code == 422
