"""Point 6 hardening — server-derived bid total is drift-proof.

`compute_total_amount` is the single server-side source of truth for a
structured bid's total_amount: it sums the same Decimal line math the draft
routes persist, so the stored total can never drift from the line items and a
client-side JS float is never trusted.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.models.vendor_portal import DraftLineItemInput
from app.services.vendor_portal_service import compute_total_amount


def _line(tid, **kw) -> DraftLineItemInput:
    return DraftLineItemInput(template_item_id=tid, **kw)


def test_sums_unit_price_lines_without_float_drift():
    id1, id2 = uuid4(), uuid4()
    tmap = {
        str(id1): {"item_type": "unit_price"},
        str(id2): {"item_type": "unit_price"},
    }
    items = [
        _line(id1, quantity=Decimal("0.1"), unit_price=Decimal("0.1")),
        _line(id2, quantity=Decimal("0.1"), unit_price=Decimal("0.1")),
    ]
    # Exact Decimal; the old JS-float path produced 0.020000000000000004,
    # which then failed the submit-time "total == sum of lines" check.
    assert compute_total_amount(items, tmap) == Decimal("0.02")


def test_mixed_unit_price_and_lump_sum():
    id1, id2 = uuid4(), uuid4()
    tmap = {
        str(id1): {"item_type": "unit_price"},
        str(id2): {"item_type": "lump_sum"},
    }
    items = [
        _line(id1, quantity=Decimal("3"), unit_price=Decimal("1250.50")),
        _line(id2, lump_sum_amount=Decimal("500")),
    ]
    assert compute_total_amount(items, tmap) == Decimal("4251.50")


def test_skips_unknown_template_ids():
    known = uuid4()
    tmap = {str(known): {"item_type": "unit_price"}}
    items = [
        _line(known, quantity=Decimal("2"), unit_price=Decimal("10")),
        # not in the template map — skipped here (build_line_item_rows raises
        # the 422 for it), so it never inflates the total.
        _line(uuid4(), quantity=Decimal("99"), unit_price=Decimal("99")),
    ]
    assert compute_total_amount(items, tmap) == Decimal("20")


def test_empty_is_zero():
    assert compute_total_amount([], {}) == Decimal("0")


def test_missing_inputs_count_as_zero():
    """Partial drafts (qty/price not yet entered) contribute 0, never crash."""
    id1 = uuid4()
    tmap = {str(id1): {"item_type": "unit_price"}}
    assert compute_total_amount([_line(id1)], tmap) == Decimal("0")
