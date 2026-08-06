import { describe, it, expect } from 'vitest';
import { prefillToHydration, toNum } from '../prefill';
import { makeRevisionPrefillLineItem } from '../../test/fixtures';
import type { RevisionPrefillResponse } from '../../types/portal';

describe('toNum', () => {
  it('parses a decimal string to a number', () => {
    expect(toNum('2500.00')).toBe(2500);
    expect(toNum('52800.0')).toBe(52800);
    expect(toNum('0')).toBe(0);
    expect(toNum('0.5')).toBe(0.5);
  });

  it('treats null and empty string as absent', () => {
    expect(toNum(null)).toBeNull();
    expect(toNum('')).toBeNull();
  });

  it('returns null rather than NaN for a non-numeric string', () => {
    // NaN would flow into the pricing state and surface as a blank or "NaN"
    // in the form instead of an empty field.
    expect(toNum('abc')).toBeNull();
    expect(toNum('12abc')).toBeNull();
    expect(Number.isNaN(toNum('abc') as number)).toBe(false);
  });

  it('returns null for a non-finite value', () => {
    expect(toNum('Infinity')).toBeNull();
    expect(toNum('-Infinity')).toBeNull();
  });

  it('keeps a legitimate zero, which is distinct from absent', () => {
    expect(toNum('0.00')).toBe(0);
    expect(toNum('0.00')).not.toBeNull();
  });
});

describe('prefillToHydration', () => {
  function prefill(overrides: Partial<RevisionPrefillResponse> = {}): RevisionPrefillResponse {
    return {
      total_amount: '2500.00',
      vendor_notes: 'prior notes',
      proposed_start_date: '2026-09-20',
      line_items: [],
      attachment_ids: [],
      ...overrides,
    };
  }

  it('converts the total to a number and passes text fields through', () => {
    const result = prefillToHydration(prefill());

    expect(result.total_amount).toBe(2500);
    expect(typeof result.total_amount).toBe('number');
    expect(result.vendor_notes).toBe('prior notes');
    expect(result.proposed_start_date).toBe('2026-09-20');
  });

  it('converts every numeric field on each line item', () => {
    const result = prefillToHydration(
      prefill({
        line_items: [
          makeRevisionPrefillLineItem({
            template_item_id: 'ti-1',
            item_type: 'unit_price',
            quantity: '300',
            unit_price: '100.50',
          }),
          makeRevisionPrefillLineItem({
            template_item_id: 'ti-2',
            lump_sum_amount: '12500.00',
          }),
        ],
      }),
    );

    expect(result.line_items).toEqual([
      { template_item_id: 'ti-1', quantity: 300, unit_price: 100.5, lump_sum_amount: null },
      { template_item_id: 'ti-2', quantity: null, unit_price: null, lump_sum_amount: 12500 },
    ]);
  });

  it('carries a null total through as null', () => {
    expect(prefillToHydration(prefill({ total_amount: null })).total_amount).toBeNull();
  });

  it('carries a null proposed start date through', () => {
    expect(
      prefillToHydration(prefill({ proposed_start_date: null })).proposed_start_date,
    ).toBeNull();
  });

  it('drops attachment_ids, which the form state does not hold', () => {
    const result = prefillToHydration(prefill({ attachment_ids: ['att-1'] }));

    expect(result).not.toHaveProperty('attachment_ids');
  });
});
