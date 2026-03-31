import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';

// Mock the API module
vi.mock('@/features/vendors/api/nearby-vendors.queries', () => ({
  fetchNearbyVendors: vi.fn(),
}));

import { fetchNearbyVendors } from '@/features/vendors/api/nearby-vendors.queries';
import { useNearbyVendors } from '../useNearbyVendors';

const mockFetchNearbyVendors = vi.mocked(fetchNearbyVendors);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useNearbyVendors', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches nearby vendors for a project', async () => {
    const mockData = [
      { id: 'v1', company_name: 'Test Vendor', distance_miles: 12.5 },
    ];
    mockFetchNearbyVendors.mockResolvedValueOnce(mockData);

    const { result } = renderHook(
      () => useNearbyVendors({ projectId: 'p1', radius: 75 }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockData);
    expect(mockFetchNearbyVendors).toHaveBeenCalledWith('p1', { radius: 75 });
  });

  it('handles API errors without crashing', async () => {
    mockFetchNearbyVendors.mockRejectedValueOnce(new Error('Network error'));

    const { result } = renderHook(
      () => useNearbyVendors({ projectId: 'p1', radius: 75 }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toBeTruthy();
  });

  it('is disabled when projectId is not provided', () => {
    const { result } = renderHook(
      () => useNearbyVendors({ projectId: null, radius: 75 }),
      { wrapper: createWrapper() },
    );

    // Should not fetch when projectId is null
    expect(result.current.isFetching).toBe(false);
    expect(mockFetchNearbyVendors).not.toHaveBeenCalled();
  });

  it('passes trade_id filter when provided', async () => {
    mockFetchNearbyVendors.mockResolvedValueOnce([]);

    const { result } = renderHook(
      () => useNearbyVendors({ projectId: 'p1', radius: 75, tradeId: 't1' }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockFetchNearbyVendors).toHaveBeenCalledWith('p1', {
      radius: 75,
      tradeId: 't1',
    });
  });
});
