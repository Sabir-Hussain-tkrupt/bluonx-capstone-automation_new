"""Pure-function tests for `check_vendor_capacity` (Task 9.1).

  max_active_jobs NULL                  → SKIPPED (uncollected data; don't penalize)
  current_active_jobs >= max_active_jobs → WARN   (at/over capacity)
  else                                  → PASS
App code never mutates capacity here — the +1 is the trigger's job.
"""

from __future__ import annotations

from app.services.pre_award_validation_service import check_vendor_capacity


def test_null_max_skipped():
    r = check_vendor_capacity(max_active_jobs=None, current_active_jobs=3)
    assert r["check"] == "vendor_capacity"
    assert r["severity"] == "skipped"
    assert r["status"] == "skipped"


def test_at_capacity_warns():
    r = check_vendor_capacity(max_active_jobs=5, current_active_jobs=5)
    assert r["severity"] == "warn"
    assert r["status"] == "fail"


def test_over_capacity_warns():
    r = check_vendor_capacity(max_active_jobs=5, current_active_jobs=6)
    assert r["severity"] == "warn"


def test_under_capacity_passes():
    r = check_vendor_capacity(max_active_jobs=5, current_active_jobs=2)
    assert r["severity"] == "pass"
    assert r["status"] == "pass"
