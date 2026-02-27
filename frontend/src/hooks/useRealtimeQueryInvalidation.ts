import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { QueryKey } from '@tanstack/react-query';
import { useRealtimeSubscription } from '@/hooks/useRealtimeSubscription';
import type {
  TableName,
  RealtimeSubscriptionConfig,
  RealtimePayload,
  UseRealtimeSubscriptionReturn,
} from '@/types/realtime.types';

interface UseRealtimeQueryInvalidationOptions<T extends TableName> {
  /** Which table/event to watch. */
  config: RealtimeSubscriptionConfig<T>;

  /**
   * The React Query key(s) to invalidate when a change is received.
   *
   * @example
   * queryKeys: [['bid_submissions', taskId]]
   * // or multiple:
   * queryKeys: [['bid_submissions', taskId], ['bid_summary', taskId]]
   */
  queryKeys: QueryKey[];

  /**
   * Optional predicate — if provided, only invalidates when this returns true.
   * Useful to avoid unnecessary re-fetches.
   */
  shouldInvalidate?: (payload: RealtimePayload<T>) => boolean;

  /** Whether the subscription is active. Defaults to true. */
  enabled?: boolean;
}

/**
 * Subscribes to real-time changes and automatically invalidates
 * React Query caches when matching events arrive.
 *
 * This is the recommended way to keep list/detail views fresh when
 * other users (or the vendor portal) modify data.
 *
 * NOTE: Requires a `QueryClientProvider` ancestor (set up in Task 2.4).
 *
 * @example Keep bid list fresh when new submissions come in:
 * ```tsx
 * useRealtimeQueryInvalidation({
 *   config: { table: 'bid_submissions', event: 'INSERT' },
 *   queryKeys: [['bid_submissions', taskId]],
 *   enabled: !!taskId,
 * });
 * ```
 */
export function useRealtimeQueryInvalidation<T extends TableName>(
  options: UseRealtimeQueryInvalidationOptions<T>,
): UseRealtimeSubscriptionReturn {
  const { config, queryKeys, shouldInvalidate, enabled = true } = options;
  const queryClient = useQueryClient();

  const handleData = useCallback(
    (payload: RealtimePayload<T>) => {
      if (shouldInvalidate && !shouldInvalidate(payload)) {
        return;
      }

      for (const key of queryKeys) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
    // Serialize queryKeys to avoid reference equality issues —
    // query keys are always JSON-serializable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, JSON.stringify(queryKeys), shouldInvalidate],
  );

  return useRealtimeSubscription({
    config,
    onData: handleData,
    enabled,
  });
}
