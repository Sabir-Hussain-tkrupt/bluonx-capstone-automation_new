import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';

vi.mock('@/features/dashboard/api/dashboard.queries', () => ({
  fetchOpenTaskCount: vi.fn(),
  fetchPendingBidCount: vi.fn(),
}));

import {
  fetchOpenTaskCount,
  fetchPendingBidCount,
} from '@/features/dashboard/api/dashboard.queries';
import { useDashboardCounts } from '../useDashboardCounts';

const mockFetchOpenTaskCount = vi.mocked(fetchOpenTaskCount);
const mockFetchPendingBidCount = vi.mocked(fetchPendingBidCount);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useDashboardCounts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns openTaskCount and pendingBidCount when both queries succeed', async () => {
    mockFetchOpenTaskCount.mockResolvedValueOnce(7);
    mockFetchPendingBidCount.mockResolvedValueOnce(3);

    const { result } = renderHook(() => useDashboardCounts(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.openTaskCount).toBe(7);
    expect(result.current.pendingBidCount).toBe(3);
  });

  it('returns 0 for counts when database is empty', async () => {
    mockFetchOpenTaskCount.mockResolvedValueOnce(0);
    mockFetchPendingBidCount.mockResolvedValueOnce(0);

    const { result } = renderHook(() => useDashboardCounts(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.openTaskCount).toBe(0);
    expect(result.current.pendingBidCount).toBe(0);
  });

  it('isLoading is true while queries are in flight', () => {
    mockFetchOpenTaskCount.mockImplementation(() => new Promise(() => {}));
    mockFetchPendingBidCount.mockImplementation(() => new Promise(() => {}));

    const { result } = renderHook(() => useDashboardCounts(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.openTaskCount).toBeUndefined();
    expect(result.current.pendingBidCount).toBeUndefined();
  });

  it('isLoading remains true when only openTaskCount has resolved', async () => {
    mockFetchOpenTaskCount.mockResolvedValueOnce(5);
    mockFetchPendingBidCount.mockImplementation(() => new Promise(() => {}));

    const { result } = renderHook(() => useDashboardCounts(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.openTaskCount).toBe(5));

    expect(result.current.isLoading).toBe(true);
  });

  it('isLoading is false and openTaskCount is undefined when openTaskCount query errors', async () => {
    mockFetchOpenTaskCount.mockRejectedValueOnce(new Error('DB error'));
    mockFetchPendingBidCount.mockResolvedValueOnce(2);

    const { result } = renderHook(() => useDashboardCounts(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.openTaskCount).toBeUndefined();
    expect(result.current.pendingBidCount).toBe(2);
  });

  it('isLoading is false and pendingBidCount is undefined when pendingBidCount query errors', async () => {
    mockFetchOpenTaskCount.mockResolvedValueOnce(4);
    mockFetchPendingBidCount.mockRejectedValueOnce(new Error('RLS denied'));

    const { result } = renderHook(() => useDashboardCounts(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.openTaskCount).toBe(4);
    expect(result.current.pendingBidCount).toBeUndefined();
  });

  it('calls fetchOpenTaskCount and fetchPendingBidCount with no arguments', async () => {
    mockFetchOpenTaskCount.mockResolvedValueOnce(1);
    mockFetchPendingBidCount.mockResolvedValueOnce(1);

    const { result } = renderHook(() => useDashboardCounts(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(mockFetchOpenTaskCount).toHaveBeenCalledWith();
    expect(mockFetchPendingBidCount).toHaveBeenCalledWith();
  });
});
