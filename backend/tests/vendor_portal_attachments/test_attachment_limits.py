"""Per-submission attachment quota — pure guard + usage query.

Bounds storage abuse on the vendor upload endpoint: a submission may hold at
most MAX_ATTACHMENTS_PER_SUBMISSION files totalling MAX_ATTACHMENT_TOTAL_BYTES.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.services.vendor_portal_service import (
    MAX_ATTACHMENT_TOTAL_BYTES,
    MAX_ATTACHMENTS_PER_SUBMISSION,
    enforce_attachment_limits,
    fetch_attachment_usage,
)


def _expect_409(fn) -> HTTPException:
    with pytest.raises(HTTPException) as exc:
        fn()
    assert exc.value.status_code == 409
    return exc.value


class TestEnforceAttachmentLimits:
    def test_under_both_caps_passes(self):
        enforce_attachment_limits(0, 0, 1024)
        enforce_attachment_limits(MAX_ATTACHMENTS_PER_SUBMISSION - 1, 0, 1024)

    def test_count_at_cap_rejected(self):
        exc = _expect_409(
            lambda: enforce_attachment_limits(MAX_ATTACHMENTS_PER_SUBMISSION, 0, 1)
        )
        assert "maximum" in str(exc.detail).lower()

    def test_count_over_cap_rejected(self):
        _expect_409(
            lambda: enforce_attachment_limits(MAX_ATTACHMENTS_PER_SUBMISSION + 5, 0, 1)
        )

    def test_aggregate_exactly_at_limit_passes(self):
        # existing + new == limit is allowed (the cap is "> limit" rejects).
        enforce_attachment_limits(1, MAX_ATTACHMENT_TOTAL_BYTES - 100, 100)

    def test_aggregate_one_over_limit_rejected(self):
        exc = _expect_409(
            lambda: enforce_attachment_limits(1, MAX_ATTACHMENT_TOTAL_BYTES - 100, 101)
        )
        assert "total" in str(exc.detail).lower()

    def test_count_cap_takes_precedence_over_size(self):
        # At the count cap even with zero new bytes → the count message wins.
        exc = _expect_409(
            lambda: enforce_attachment_limits(MAX_ATTACHMENTS_PER_SUBMISSION, 0, 0)
        )
        assert "attachments" in str(exc.detail).lower()


def _fake_db(rows):
    db = MagicMock()
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.execute.return_value = MagicMock(data=rows)
    db.table.return_value = chain
    return db


class TestFetchAttachmentUsage:
    def test_counts_and_sums_file_sizes(self):
        db = _fake_db([{"file_size": 100}, {"file_size": 250}, {"file_size": 0}])
        assert fetch_attachment_usage(db, "sub-1") == (3, 350)

    def test_empty_is_zero(self):
        assert fetch_attachment_usage(_fake_db([]), "sub-1") == (0, 0)

    def test_null_file_size_treated_as_zero(self):
        db = _fake_db([{"file_size": None}, {"file_size": 500}])
        assert fetch_attachment_usage(db, "sub-1") == (2, 500)
