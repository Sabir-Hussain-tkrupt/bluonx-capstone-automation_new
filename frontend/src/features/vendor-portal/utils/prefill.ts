/**
 * Revision-prefill conversion.
 *
 * The prefill endpoint returns money and quantity fields as strings (Pydantic
 * serializes Decimal that way), but the bid form state holds numbers. This is
 * the single place that translation happens, so the form never has to guess
 * whether a value is `'2500.00'` or `2500`.
 */
import type { PrefillHydration } from '../hooks/useBidFormState';
import type { RevisionPrefillResponse } from '../types/portal';

/**
 * Decimal strings (Pydantic Decimal over the wire) → `number | null`.
 *
 * Anything not a finite number becomes `null` rather than `NaN`: a `NaN` in
 * the pricing state would propagate silently through the totals and render as
 * a blank or "NaN" in the form.
 */
export function toNum(v: string | null): number | null {
  if (v == null || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** Wire-shape prefill → the numeric shape `hydrateFromPrefill` expects. */
export function prefillToHydration(pf: RevisionPrefillResponse): PrefillHydration {
  return {
    vendor_notes: pf.vendor_notes,
    total_amount: toNum(pf.total_amount),
    proposed_start_date: pf.proposed_start_date,
    line_items: pf.line_items.map((li) => ({
      template_item_id: li.template_item_id,
      quantity: toNum(li.quantity),
      unit_price: toNum(li.unit_price),
      lump_sum_amount: toNum(li.lump_sum_amount),
    })),
  };
}
