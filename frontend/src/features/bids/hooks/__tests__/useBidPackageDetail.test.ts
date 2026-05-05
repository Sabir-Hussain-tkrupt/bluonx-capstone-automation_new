import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';

vi.mock('@/features/bids/api/bid-package.queries', () => ({
  fetchBidPackageDetail: vi.fn(),
}));

import { fetchBidPackageDetail } from '@/features/bids/api/bid-package.queries';
import type { BidPackageDetail } from '@/features/bids/types';
import { useBidPackageDetail } from '../useBidPackageDetail';

const mockFetch = vi.mocked(fetchBidPackageDetail);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

function basePayload(overrides: Partial<BidPackageDetail> = {}): BidPackageDetail {
  return {
    id: 'bp-1',
    task_name: 'Rough Grading',
    round_number: 1,
    deadline: '2026-06-01T00:00:00Z',
    status: 'open',
    instructions: null,
    bid_template: null,
    documents: [],
    invitation_summary: {
      total: 0,
      sent: 0,
      opened: 0,
      submitted: 0,
      declined: 0,
      expired: 0,
      no_response: 0,
    },
    invitations: [],
    submitted_bids: [],
    ...overrides,
  };
}

describe('useBidPackageDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('exposes submitted_bids from the API payload', async () => {
    const submitted = [
      { vendor_company_name: 'Bedrock Civil', total_amount: 41200 },
      { vendor_company_name: 'Apex Grading', total_amount: 47500 },
    ];
    mockFetch.mockResolvedValueOnce(basePayload({ submitted_bids: submitted }));

    const { result } = renderHook(() => useBidPackageDetail('bp-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.submitted_bids).toEqual(submitted);
  });

  it('handles a payload with empty submitted_bids', async () => {
    mockFetch.mockResolvedValueOnce(basePayload({ submitted_bids: [] }));

    const { result } = renderHook(() => useBidPackageDetail('bp-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data?.submitted_bids).toEqual([]);
  });
});
