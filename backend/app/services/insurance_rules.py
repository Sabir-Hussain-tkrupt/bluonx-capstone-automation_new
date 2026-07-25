"""
Insurance validity classification — the single source of truth for how a
vendor's insurance certificate is judged against a project.

Pure, no I/O. Shared by two stages that must never disagree:
  - vendor filtering (services/vendor_filtering.py): decides bid eligibility.
  - pre-award validation (services/pre_award_validation_service.py): the gate
    at award time.

Each caller maps the classification to its own output shape and severity
(the filter disqualifies on "expired"/"missing" and treats "lapses_before_end"
as a non-blocking advisory; pre-award BLOCKs on "expired", WARNs on the other
two). This module only classifies.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

InsuranceStatus = Literal["missing", "expired", "lapses_before_end", "ok"]


def classify_insurance(
    expiration: date | None,
    project_end: date | None,
    today: date,
) -> InsuranceStatus:
    """Classify a vendor's insurance against today and the project horizon.

    - "missing"           : no certificate on file (expiration is None).
    - "expired"           : certificate lapsed before today. Hard problem —
                            the vendor is uninsured right now.
    - "lapses_before_end" : valid today, but ends before the project's
                            estimated end date. A coverage-gap caution, not an
                            immediate blocker.
    - "ok"                : valid today and through the project horizon (or no
                            horizon is known).

    Uses strict `<`, so a certificate expiring exactly on `today` (still valid
    through today) or exactly on `project_end` (covers the whole project) is
    "ok", not flagged. This matches check_insurance_validity's boundaries.

    project_end is None (no estimated end date) collapses to a today-only
    check: anything not already expired is "ok". This is why an overdue
    project (a past project_end) cannot produce a spurious result — see the
    filter, which passes project_end only when it is a real future horizon by
    virtue of comparing against a not-yet-expired certificate.
    """
    if expiration is None:
        return "missing"
    if expiration < today:
        return "expired"
    if project_end is not None and expiration < project_end:
        return "lapses_before_end"
    return "ok"
