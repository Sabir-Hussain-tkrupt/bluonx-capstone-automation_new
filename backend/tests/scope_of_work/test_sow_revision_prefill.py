"""Signed Scope of Work — revision must re-attest (never prefilled).

The revision-prefill response must NOT carry any SoW attestation field, so the
vendor is forced to re-type it fresh each round.
"""

from __future__ import annotations

from app.models.vendor_portal import RevisionPrefillResponse


def test_revision_prefill_carries_no_attestation():
    fields = set(RevisionPrefillResponse.model_fields)
    assert "sow_attested_name" not in fields
    assert "sow_attested_at" not in fields
