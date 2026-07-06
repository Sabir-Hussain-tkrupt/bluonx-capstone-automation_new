"""Signed Scope of Work — submit-time attestation validation.

The vendor must type their company name in CAPS to attest to the package SoW.
This is UNCONDITIONAL at submit (every package has a SoW). Pure-function tests
against validate_for_submit.
"""

from __future__ import annotations

from app.services.vendor_portal_submit_validator import validate_for_submit


def _submission(sow_attested_name):
    return {
        "vendor_notes": "",
        "total_amount": "1000.00",
        "sow_attested_name": sow_attested_name,
    }


def _validate(sow_attested_name):
    # Lump-sum template → per-line checks skipped, isolating the attestation rule.
    return validate_for_submit(
        submission=_submission(sow_attested_name),
        line_items=[],
        template_items=[],
        is_lump_sum_template=True,
    )


def _fields(errors):
    return [e.field for e in errors]


def test_empty_attestation_is_rejected():
    errors = _validate("")
    assert "sow_attested_name" in _fields(errors)


def test_none_attestation_is_rejected():
    errors = _validate(None)
    assert "sow_attested_name" in _fields(errors)


def test_whitespace_only_attestation_is_rejected():
    errors = _validate("   ")
    assert "sow_attested_name" in _fields(errors)


def test_non_caps_attestation_is_rejected():
    errors = _validate("Acme Grading")
    sow_errors = [e for e in errors if e.field == "sow_attested_name"]
    assert sow_errors, "expected a CAPS error"
    assert "capital" in sow_errors[0].message.lower()


def test_caps_attestation_passes():
    errors = _validate("ACME GRADING LLC")
    assert "sow_attested_name" not in _fields(errors)


def test_caps_with_punctuation_passes():
    # Digits/punctuation equal their own upper() — only lowercase letters fail.
    errors = _validate("ACME GRADING #1, LLC.")
    assert "sow_attested_name" not in _fields(errors)
