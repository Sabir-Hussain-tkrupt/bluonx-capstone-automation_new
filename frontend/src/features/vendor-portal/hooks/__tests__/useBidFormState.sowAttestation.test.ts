import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useBidFormState, type PrefillHydration } from '../useBidFormState';
import type { BidDraft, PortalBidTemplate } from '../../types/portal';

const lumpTemplate: PortalBidTemplate = {
  id: 'tpl',
  name: 'Lump sum',
  is_lump_sum: true,
  items: [],
};

const draftWithAttestation: BidDraft = {
  id: 'draft-1',
  vendor_notes: 'hi',
  total_amount: 1000,
  line_items: [],
  attachment_ids: [],
  last_saved_at: '2026-06-04T00:00:00Z',
  proposed_start_date: null,
  sow_attested_name: 'ACME GRADING',
};

const prefill: PrefillHydration = {
  total_amount: 2500,
  vendor_notes: 'prior notes',
  proposed_start_date: '2026-09-20',
  line_items: [],
};

describe('useBidFormState — SoW attestation plumbing', () => {
  it('initial state has an empty attestation', () => {
    const { result } = renderHook(() => useBidFormState(lumpTemplate));
    expect(result.current.state.companyInfo.sow_attested_name).toBe('');
  });

  it('updateSowAttestation auto-uppercases and marks dirty', () => {
    const { result } = renderHook(() => useBidFormState(lumpTemplate));
    act(() => result.current.updateSowAttestation('acme grading'));
    expect(result.current.state.companyInfo.sow_attested_name).toBe('ACME GRADING');
    expect(result.current.state.dirty).toBe(true);
  });

  it('HYDRATE_FROM_DRAFT restores the saved attestation', () => {
    const { result } = renderHook(() => useBidFormState(lumpTemplate));
    act(() => result.current.hydrateFromDraft(draftWithAttestation));
    expect(result.current.state.companyInfo.sow_attested_name).toBe('ACME GRADING');
  });

  it('HYDRATE_FROM_PREFILL (revision) leaves the attestation empty — must re-attest', () => {
    const { result } = renderHook(() => useBidFormState(lumpTemplate));
    act(() => result.current.hydrateFromPrefill(prefill));
    expect(result.current.state.companyInfo.sow_attested_name).toBe('');
  });
});
