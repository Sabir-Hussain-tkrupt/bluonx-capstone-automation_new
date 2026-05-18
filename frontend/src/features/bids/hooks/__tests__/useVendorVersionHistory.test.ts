import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';

vi.mock('@/features/bids/api/bid-package.queries', () => ({
  fetchBidSubmissionDetail: vi.fn(),
}));

import { fetchBidSubmissionDetail } from '@/features/bids/api/bid-package.queries';
import type { BidSubmissionDetail } from '@/features/bids/types';
import { useVendorVersionHistory } from '../useVendorVersionHistory';

const mockFetch = vi.mocked(fetchBidSubmissionDetail);

function sub(
  over: Partial<BidSubmissionDetail> & { id: string },
): BidSubmissionDetail {
  return {
    bid_invitation_id: 'inv-1',
    status: 'submitted',
    is_direct_assign: false,
    is_superseded: false,
    is_draft: false,
    revision_number: 1,
    supersedes_submission_id: null,
    total_amount: 1000,
    vendor_notes: null,
    submitted_at: '2026-05-01T00:00:00Z',
    vendor_company_name: 'Apex',
    vendor_contact_name: null,
    vendor_contact_email: null,
    line_items: [],
    attachments: [],
    ...over,
  };
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useVendorVersionHistory — draft skipping', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('skips a draft hop but keeps walking the chain via its predecessor', async () => {
    const chain: Record<string, BidSubmissionDetail> = {
      v2: sub({
        id: 'v2',
        revision_number: 2,
        supersedes_submission_id: 'draft',
      }),
      draft: sub({
        id: 'draft',
        is_draft: true,
        revision_number: 2,
        supersedes_submission_id: 'v1',
      }),
      v1: sub({ id: 'v1', revision_number: 1, supersedes_submission_id: null }),
    };
    mockFetch.mockImplementation((id: string) =>
      Promise.resolve(chain[id]),
    );

    const { result } = renderHook(
      () => useVendorVersionHistory('v2', true),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.map((s) => s.id)).toEqual(['v1', 'v2']);
  });

  it('returns predecessor-only history when the starting submission is a draft (defensive)', async () => {
    const chain: Record<string, BidSubmissionDetail> = {
      d: sub({
        id: 'd',
        is_draft: true,
        revision_number: 2,
        supersedes_submission_id: 'v1',
      }),
      v1: sub({ id: 'v1', revision_number: 1, supersedes_submission_id: null }),
    };
    mockFetch.mockImplementation((id: string) =>
      Promise.resolve(chain[id]),
    );

    const { result } = renderHook(() => useVendorVersionHistory('d', true), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.map((s) => s.id)).toEqual(['v1']);
  });
});
