import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useBidFormState } from '../useBidFormState';
import type {
  BidDraft,
  PortalBidTemplate,
  RevisionPrefillResponse,
} from '../../types/portal';

const lumpTemplate: PortalBidTemplate = {
  id: 'tpl',
  name: 'Lump sum',
  is_lump_sum: true,
  items: [],
};

const draft: BidDraft = {
  id: 'draft-1',
  vendor_notes: 'hi',
  total_amount: 1000,
  line_items: [],
  attachment_ids: [],
  last_saved_at: '2026-06-04T00:00:00Z',
  proposed_start_date: '2026-09-15',
};

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
    act(() => result.current.hydrateFromPrefill(prefill));
    expect(result.current.state.companyInfo.proposed_start_date).toBe('2026-09-20');
  });

  it('updateProposedStartDate replaces the date and marks the form dirty', () => {
    const { result } = renderHook(() => useBidFormState(lumpTemplate));
    act(() => result.current.updateProposedStartDate('2026-10-05'));
    expect(result.current.state.companyInfo.proposed_start_date).toBe('2026-10-05');
    expect(result.current.state.dirty).toBe(true);
  });
});
