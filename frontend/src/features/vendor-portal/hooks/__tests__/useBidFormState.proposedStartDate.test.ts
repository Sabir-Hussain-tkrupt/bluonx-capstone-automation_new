import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useBidFormState } from '../useBidFormState';
import { prefillToHydration } from '../../utils/prefill';
import { makeBidDraft, makePortalBidTemplate } from '../../test/fixtures';
import type { RevisionPrefillResponse } from '../../types/portal';

const lumpTemplate = makePortalBidTemplate();

const draft = makeBidDraft({
  vendor_notes: 'hi',
  total_amount: 1000,
  proposed_start_date: '2026-09-15',
});

// The wire shape: decimals arrive as strings. Hydration goes through
// `prefillToHydration` exactly as BidFormPage does, so this exercises the real
// conversion rather than hand-feeding the hook an already-numeric object.
const prefill: RevisionPrefillResponse = {
  total_amount: '2500.00',
  vendor_notes: 'prior notes',
  line_items: [],
  attachment_ids: [],
  proposed_start_date: '2026-09-20',
};

describe('useBidFormState — proposed_start_date plumbing', () => {
  it('initial state has proposed_start_date: null on companyInfo', () => {
    const { result } = renderHook(() => useBidFormState(lumpTemplate));
    expect(result.current.state.companyInfo.proposed_start_date).toBeNull();
  });

  it('HYDRATE_FROM_DRAFT copies proposed_start_date from the draft', () => {
    const { result } = renderHook(() => useBidFormState(lumpTemplate));
    act(() => result.current.hydrateFromDraft(draft));
    expect(result.current.state.companyInfo.proposed_start_date).toBe('2026-09-15');
  });

  it('HYDRATE_FROM_PREFILL copies proposed_start_date from the prefill', () => {
    const { result } = renderHook(() => useBidFormState(lumpTemplate));
    act(() => result.current.hydrateFromPrefill(prefillToHydration(prefill)));
    expect(result.current.state.companyInfo.proposed_start_date).toBe('2026-09-20');
  });

  it('HYDRATE_FROM_PREFILL lands the total as a number, not the wire string', () => {
    const { result } = renderHook(() => useBidFormState(lumpTemplate));
    act(() => result.current.hydrateFromPrefill(prefillToHydration(prefill)));
    expect(result.current.state.pricing.total_amount).toBe(2500);
    expect(typeof result.current.state.pricing.total_amount).toBe('number');
  });

  it('updateProposedStartDate replaces the date and marks the form dirty', () => {
    const { result } = renderHook(() => useBidFormState(lumpTemplate));
    act(() => result.current.updateProposedStartDate('2026-10-05'));
    expect(result.current.state.companyInfo.proposed_start_date).toBe('2026-10-05');
    expect(result.current.state.dirty).toBe(true);
  });
});
