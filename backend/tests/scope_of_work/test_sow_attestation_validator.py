"""Signed Scope of Work — submit-time signature validation.

The vendor "signs" by typing their company name. It is UNCONDITIONALLY required
at submit and must match the name on file (normalized: trim + collapse
whitespace, case-insensitive). Pure-function tests against validate_for_submit.
"""

from __future__ import annotations

from app.services.vendor_portal_submit_validator import validate_for_submit

COMPANY = "Acme Grading"


def _validate(sow_attested_name, *, company=COMPANY):
    # Lump-sum template → per-line checks skipped, isolating the signature rule.
    return validate_for_submit(
        submission={
            "vendor_notes": "",
            "total_amount": "1000.00",
            "sow_attested_name": sow_attested_name,
        },
        line_items=[],
        template_items=[],
        is_lump_sum_template=True,
        vendor_company_name=company,
    )


def _fields(errors):
    return [e.field for e in errors]


def test_empty_signature_is_rejected():
    assert "sow_attested_name" in _fields(_validate(""))


def test_none_signature_is_rejected():
    assert "sow_attested_name" in _fields(_validate(None))


def test_whitespace_only_signature_is_rejected():
    assert "sow_attested_name" in _fields(_validate("   "))


def test_mismatched_name_is_rejected():
    errors = [e for e in _validate("Some Other Co") if e.field == "sow_attested_name"]
    assert errors
    assert "match" in errors[0].message.lower()


def test_exact_match_passes():
    assert "sow_attested_name" not in _fields(_validate("Acme Grading"))


def test_match_is_case_insensitive():
    assert "sow_attested_name" not in _fields(_validate("ACME GRADING"))
    assert "sow_attested_name" not in _fields(_validate("acme grading"))


def test_match_tolerates_whitespace():
    assert "sow_attested_name" not in _fields(_validate("  ACME   GRADING "))


def test_punctuation_difference_is_rejected():
    assert "sow_attested_name" in _fields(_validate("Acme Grading, LLC"))


def test_without_company_name_falls_back_to_presence_only():
    # Defensive: if the caller can't resolve the company name, presence is still
    # enforced but the match is skipped (the router always supplies the name).
    assert "sow_attested_name" in _fields(_validate("", company=None))
    assert "sow_attested_name" not in _fields(_validate("Anything", company=None))
