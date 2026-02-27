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
      retry: 2,

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
