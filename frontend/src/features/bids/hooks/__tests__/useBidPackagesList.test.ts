import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';

vi.mock('@/features/bids/api/bid-packages-list.queries', () => ({
  fetchBidPackagesList: vi.fn(),
}));

import { fetchBidPackagesList } from '@/features/bids/api/bid-packages-list.queries';
import type { BidPackagesListRow } from '@/features/bids/api/bid-packages-list.queries';
import { useBidPackagesList } from '../useBidPackagesList';

const mockFetch = vi.mocked(fetchBidPackagesList);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

const sampleItems: BidPackagesListRow[] = [
  {
    id: 'p1',
    task_id: 't1',
    task_name: 'Rough Grading',
    project_id: 'pr1',
    project_name: 'Alpine Estates',
    round_number: 1,
    deadline: '2026-06-01T00:00:00Z',
    status: 'open',
    total_invitations: 5,
    submitted_count: 2,
    created_at: '2026-04-01T00:00:00Z',
  },
];

describe('useBidPackagesList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns items when fetch succeeds', async () => {
    mockFetch.mockResolvedValueOnce(sampleItems);

    const { result } = renderHook(() => useBidPackagesList(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.data).toEqual(sampleItems);
    expect(result.current.isError).toBe(false);
  });

  it('passes filters through to fetchBidPackagesList', async () => {
    mockFetch.mockResolvedValueOnce([]);

    const filters = {
      status: 'open' as const,
      project_id: 'pr1',
      sort_by: 'deadline' as const,
      sort_order: 'asc' as const,
    };

    const { result } = renderHook(() => useBidPackagesList(filters), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockFetch).toHaveBeenCalledWith(filters);
  });

  it('exposes isLoading=true while pending', () => {
    mockFetch.mockImplementation(() => new Promise(() => {}));

    const { result } = renderHook(() => useBidPackagesList(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.data).toBeUndefined();
  });

  it('exposes isError on fetch rejection', async () => {
    mockFetch.mockRejectedValueOnce(new Error('boom'));

    const { result } = renderHook(() => useBidPackagesList(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.isError).toBe(true);
  });

  it('uses distinct query keys for distinct filter sets (cache isolation)', async () => {
    mockFetch.mockResolvedValue([]);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);

    const { result: a } = renderHook(
      () => useBidPackagesList({ status: 'open' }),
      { wrapper },
    );
    const { result: b } = renderHook(
      () => useBidPackagesList({ status: 'closed' }),
      { wrapper },
    );

    await waitFor(() => expect(a.current.isLoading).toBe(false));
    await waitFor(() => expect(b.current.isLoading).toBe(false));

    // If keys collided, we'd see only one fetch.
    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(mockFetch).toHaveBeenCalledWith({ status: 'open' });
    expect(mockFetch).toHaveBeenCalledWith({ status: 'closed' });
  });
});
