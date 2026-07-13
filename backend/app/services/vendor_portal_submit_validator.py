"""
Server-side submit-time validation for vendor bids (Task 5.4).

Isolated in its own module because this is the most rule-dense part of the
vendor portal and benefits from its own unit-test surface. The router calls
`validate_for_submit` once after re-reading the authoritative DB state —
never on the request body — so tampered drafts can't slip past.

Rules enforced (per Task 5.4 spec):
  1. vendor_notes length ≤ 2000
  1c. sow_attested_name present and (given the company name) matches it — the
      vendor "signs" by typing their company name. Normalized: trim + collapse
      whitespace, case-insensitive. Mirrors the frontend gate; authoritative here.
  2. total_amount > 0
  3. Structured template: len(line_items) == len(template_items)
  4. Per line, required pricing fields are present and ≥ 0 (or > 0 for qty)
  5. Each line_total equals its own math (qty × unit_price OR lump_sum_amount)
  6. total_amount equals the sum of line_totals

Deadline / package-status checks are NOT here — they live in
`assert_package_open_and_before_deadline` and run before this validator.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.vendor_portal import FieldError


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _normalize_signature(value: str | None) -> str:
    """trim → collapse internal whitespace → uppercase.

    Must stay byte-for-byte equivalent to the frontend `normalizeSignature`
    (features/vendor-portal/utils/attestation.ts) so the two gates never
    disagree on what counts as a valid signature.
    """
    return " ".join((value or "").split()).upper()


def validate_for_submit(
    submission: dict,
    line_items: list[dict],
    template_items: list[dict],
    is_lump_sum_template: bool,
    package_has_desired_date: bool = False,
    vendor_company_name: str | None = None,
) -> list[FieldError]:
    """Return an empty list if the submission is valid, else field-level errors.

    `package_has_desired_date` toggles the timeline rule (Task 8.1.5):
    when the package has a desired start date, the submission MUST carry
    a proposed_start_date; otherwise the field is informational.

    `vendor_company_name` is the name on file; when provided, the SoW
    signature must match it (normalized). The router always passes it, so the
    match is authoritative in production.
    """
    errors: list[FieldError] = []

    # 1. vendor_notes length
    notes = submission.get("vendor_notes") or ""
    if len(notes) > 2000:
        errors.append(
            FieldError(field="vendor_notes", message="Notes exceed 2000 characters")
        )

    # 1b. proposed_start_date required when package has a desired date
    if package_has_desired_date:
        proposed = submission.get("proposed_start_date")
        if proposed in (None, ""):
            errors.append(
                FieldError(
                    field="proposed_start_date",
                    message=(
                        "Proposed start date is required when the package "
                        "has a desired start date"
                    ),
                )
            )

    # 1c. Scope of Work signature — UNCONDITIONALLY required at submit. Every
    # package carries a SoW, so the vendor signs by typing their company name.
    # When we know the name on file, the signature must match it (normalized).
    attest = (submission.get("sow_attested_name") or "").strip()
    if not attest:
        errors.append(
            FieldError(
                field="sow_attested_name",
                message="You must sign by typing your company name to attest to the Scope of Work",
            )
        )
    elif vendor_company_name and _normalize_signature(attest) != _normalize_signature(
        vendor_company_name
    ):
        errors.append(
            FieldError(
                field="sow_attested_name",
                message="Your signature must match your company name",
            )
        )

    # 2. total_amount > 0
    total = _as_decimal(submission.get("total_amount"))
    if total is None or total <= 0:
        errors.append(
            FieldError(
                field="total_amount",
                message="Total bid amount must be greater than zero",
            )
        )

    # 3–6 apply to structured templates. For lump-sum templates, the vendor
    # only fills total_amount; line_items mirrors the one-row template and
    # we don't re-validate the breakdown.
    if not is_lump_sum_template:
        if len(line_items) != len(template_items):
            errors.append(
                FieldError(
                    field="line_items",
                    message=(
                        f"Expected {len(template_items)} line items, "
                        f"got {len(line_items)}"
                    ),
                )
            )

        computed_sum = Decimal("0")
        sorted_items = sorted(line_items, key=lambda r: r.get("sort_order") or 0)
        for idx, li in enumerate(sorted_items):
            path = f"line_items[{idx}]"
            item_type = li.get("item_type")
            line_total = _as_decimal(li.get("line_total")) or Decimal("0")

            if item_type == "unit_price":
                qty = _as_decimal(li.get("quantity"))
                up = _as_decimal(li.get("unit_price"))
                if qty is None or qty <= 0:
                    errors.append(
                        FieldError(
                            field=f"{path}.quantity",
                            message="Quantity is required and must be greater than zero",
                        )
                    )
                if up is None or up < 0:
                    errors.append(
                        FieldError(
                            field=f"{path}.unit_price",
                            message="Unit price is required and must be ≥ 0",
                        )
                    )
                if qty is not None and up is not None:
                    expected = qty * up
                    if line_total != expected:
                        errors.append(
                            FieldError(
                                field=f"{path}.line_total",
                                message=(
                                    "Line total does not equal quantity × unit price"
                                ),
                            )
                        )
                    computed_sum += expected
            elif item_type == "lump_sum":
                lsa = _as_decimal(li.get("lump_sum_amount"))
                if lsa is None or lsa < 0:
                    errors.append(
                        FieldError(
                            field=f"{path}.lump_sum_amount",
                            message="Lump sum amount is required and must be ≥ 0",
                        )
                    )
                if lsa is not None:
                    if line_total != lsa:
                        errors.append(
                            FieldError(
                                field=f"{path}.line_total",
                                message="Line total does not equal lump sum amount",
                            )
                        )
                    computed_sum += lsa
            else:
                errors.append(
                    FieldError(
                        field=f"{path}.item_type",
                        message=f"Unknown item_type '{item_type}'",
                    )
                )

        if total is not None and computed_sum != total:
            errors.append(
                FieldError(
                    field="total_amount",
                    message="Total amount does not match sum of line totals",
                )
            )

    return errors
