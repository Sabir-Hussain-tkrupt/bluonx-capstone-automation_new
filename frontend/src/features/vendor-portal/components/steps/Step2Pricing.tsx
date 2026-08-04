import { useState } from 'react';
import { Alert, Button, Card } from '@/components/ui';
import { useBidContext } from '../../hooks/useBidContext';
import { computeGrandTotal } from '../../hooks/useBidFormState';
import type { BidFormState, FormLineItem } from '../../types/portal';
import { LumpSumInput } from './LumpSumInput';
import { LineItemsTable } from './LineItemsTable';
import { formatCurrency } from '../../utils/currency';

export interface Step2PricingProps {
  state: BidFormState;
  onSetLumpTotal: (value: number | null) => void;
  onUpdateLineItem: (
    template_item_id: string,
    patch: Partial<Pick<FormLineItem, 'quantity' | 'unit_price' | 'lump_sum_amount'>>,
  ) => void;
  onNext: () => void;
  onBack: () => void;
  onSaveDraft: () => void;
}

function validatePricing(state: BidFormState, isLump: boolean) {
  const errors: { total?: string; lineItems: Record<string, string> } = { lineItems: {} };

  if (isLump) {
    const amount = state.pricing.total_amount;
    if (amount === null || Number.isNaN(amount)) {
      errors.total = 'Total bid amount is required.';
    } else if (amount <= 0) {
      errors.total = 'Total bid amount must be greater than zero.';
    }
    return errors;
  }

  state.pricing.line_items.forEach((item) => {
    if (item.item_type === 'lump_sum') {
      const a = item.lump_sum_amount;
      if (a === null || Number.isNaN(a)) {
        errors.lineItems[item.template_item_id] = 'Lump sum amount is required.';
      } else if (a < 0) {
        errors.lineItems[item.template_item_id] = 'Lump sum amount must be ≥ 0.';
      }
    } else {
      const q = item.quantity;
      const p = item.unit_price;
      if (q === null || Number.isNaN(q)) {
        errors.lineItems[item.template_item_id] = 'Quantity is required.';
      } else if (q <= 0) {
        // Matches the server rule (qty > 0): a per-unit line with zero units
        // is meaningless. "No cost" is expressed via unit price = 0, not qty 0.
        errors.lineItems[item.template_item_id] = 'Quantity must be greater than zero.';
      } else if (p === null || Number.isNaN(p)) {
        errors.lineItems[item.template_item_id] = 'Unit price is required.';
      } else if (p < 0) {
        errors.lineItems[item.template_item_id] = 'Unit price must be ≥ 0.';
      }
    }
  });

  const grandTotal = computeGrandTotal(state.pricing.line_items);
  if (Object.keys(errors.lineItems).length === 0 && grandTotal <= 0) {
    // Surface on the first row so the user sees it
    const first = state.pricing.line_items[0]?.template_item_id;
    if (first) {
      errors.lineItems[first] = 'Grand total must be greater than zero.';
    }
  }
  return errors;
}

export function Step2Pricing({
  state,
  onSetLumpTotal,
  onUpdateLineItem,
  onNext,
  onBack,
  onSaveDraft,
}: Step2PricingProps) {
  const { bid_template } = useBidContext();
  const [attempted, setAttempted] = useState(false);
  const isLump = bid_template.is_lump_sum;

  const errors = validatePricing(state, isLump);
  const hasErrors = !!errors.total || Object.keys(errors.lineItems).length > 0;

  function handleNext() {
    setAttempted(true);
    if (hasErrors) return;
    onNext();
  }

  const grandTotal = isLump
    ? state.pricing.total_amount ?? 0
    : computeGrandTotal(state.pricing.line_items);

  return (
    <div className="flex flex-col gap-6">
      <Card
        title={isLump ? 'Lump Sum Bid' : bid_template.name}
        subtitle={
          isLump
            ? 'Provide a single all-inclusive total for the full scope of work.'
            : 'Complete every line item. Line totals and grand total calculate automatically.'
        }
        padding="md"
      >
        {isLump ? (
          <LumpSumInput
            value={state.pricing.total_amount}
            onChange={onSetLumpTotal}
            error={attempted ? errors.total : undefined}
          />
        ) : (
          <LineItemsTable
            items={state.pricing.line_items}
            onUpdate={onUpdateLineItem}
            fieldErrors={attempted ? errors.lineItems : {}}
          />
        )}
      </Card>

      {attempted && hasErrors && (
        <Alert variant="danger" title="Please fix the highlighted items">
          All amounts must be filled in and at least one must be greater than zero.
        </Alert>
      )}

      <div className="rounded-lg border border-primary-100 bg-primary-50 px-4 py-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-primary-700">Grand Total</span>
          <span className="text-lg font-bold text-primary-700 tabular-nums">
            {formatCurrency(grandTotal)}
          </span>
        </div>
      </div>

      <div className="flex flex-col-reverse items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:gap-2">
          <Button type="button" variant="ghost" onClick={onBack}>
            ← Back
          </Button>
          <Button type="button" variant="outline" onClick={onSaveDraft}>
            Save Draft
          </Button>
        </div>
        <Button type="button" variant="primary" onClick={handleNext}>
          Next: Documents →
        </Button>
      </div>
    </div>
  );
}
