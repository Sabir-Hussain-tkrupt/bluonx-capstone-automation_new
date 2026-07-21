import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Data stays fresh for 2 minutes. During this window, component
      // remounts reuse cached data without a network request.
      // Real-time subscriptions handle truly time-sensitive data.
      staleTime: 2 * 60 * 1000,

      // Unused cache entries are garbage-collected after 10 minutes.
      gcTime: 10 * 60 * 1000,

      // Retry failed queries up to 2 times with exponential backoff.
      // Supabase PostgREST can have transient 500s; 2 retries covers that.
      //
      // 4xx responses are excluded: an expired session, a permission denial,
      // a bad filter value or a missing row fails identically on retry, so
      // retrying only delays the error the user needs to see by two backoffs.
      // Network failures (status 0) and 5xx still retry.
      retry: (failureCount, error) => {
        const status = (error as { status?: number } | null)?.status;
        if (typeof status === 'number' && status >= 400 && status < 500) {
          return false;
        }
        return failureCount < 2;
      },

      // Re-fetch stale queries when user returns to the browser tab.
      // Critical for multi-user bid management — data may change while away.
      refetchOnWindowFocus: true,

      // Re-fetch on mount if data is stale.
      refetchOnMount: true,

      // Always re-fetch on network reconnect.
      refetchOnReconnect: 'always',
    },
    mutations: {
      // Never retry mutations — writes should not be automatically retried
      // since they may cause side effects (e.g., creating duplicate vendors).
      retry: false,
    },
  },
});
