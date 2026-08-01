import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';

vi.mock('@/features/vendors/api/vendor.queries', () => ({
  fetchVendorEmailLog: vi.fn(),
}));

import { fetchVendorEmailLog } from '@/features/vendors/api/vendor.queries';
import { useVendorEmailLog } from '../useVendorEmailLog';

const mockFetch = vi.mocked(fetchVendorEmailLog);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useVendorEmailLog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches the email log when enabled is true', async () => {
    const items = [
      {
        id: 'e1',
        recipient_email: 'v@example.com',
        email_type: 'bid_invitation',
        subject: 'subj',
        status: 'sent',
        sent_at: '2026-05-30T10:00:00Z',
        error_message: null,
      },
    ];
    mockFetch.mockResolvedValueOnce({ items, total: 1, page: 1, page_size: 25 });

    const { result } = renderHook(() => useVendorEmailLog('v-1', true), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockFetch).toHaveBeenCalledWith('v-1', { page: 1, pageSize: 25 });
    expect(result.current.data?.items).toEqual(items);
    expect(result.current.data?.total).toBe(1);
  });

  it('requests the page it is given', async () => {
    mockFetch.mockResolvedValue({ items: [], total: 60, page: 3, page_size: 25 });

    const { result } = renderHook(() => useVendorEmailLog('v-1', true, 3), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(mockFetch).toHaveBeenCalledWith('v-1', { page: 3, pageSize: 25 });
  });

  it('does not fetch when enabled is false', () => {
    renderHook(() => useVendorEmailLog('v-1', false), {
      wrapper: createWrapper(),
    });

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('does not fetch when vendorId is empty', () => {
    renderHook(() => useVendorEmailLog('', true), {
      wrapper: createWrapper(),
    });

    expect(mockFetch).not.toHaveBeenCalled();
  });
});
