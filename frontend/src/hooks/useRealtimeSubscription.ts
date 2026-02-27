import { useEffect, useRef, useState } from 'react';
import type { RealtimeChannel } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';
import type {
  TableName,
  UseRealtimeSubscriptionOptions,
  UseRealtimeSubscriptionReturn,
  RealtimeSubscriptionStatus,
  RealtimePayload,
} from '@/types/realtime.types';

/**
 * Subscribe to real-time Postgres changes on a Supabase table.
 *
 * Creates a Supabase Realtime channel, subscribes to postgres_changes events,
 * and cleans up on unmount or when config changes. Designed for Phase 4+
 * bid tracking dashboard but usable anywhere.
 *
 * @example Watch all changes on bid_submissions:
 * ```tsx
 * useRealtimeSubscription({
 *   config: { table: 'bid_submissions', event: '*' },
 *   onData: (payload) => {
 *     console.log('Bid changed:', payload.eventType, payload.new);
 *   },
 * });
 * ```
 *
 * @example Filtered — only new notifications for current user:
 * ```tsx
 * useRealtimeSubscription({
 *   config: {
 *     table: 'notifications',
 *     event: 'INSERT',
 *     filter: { column: 'user_id', value: currentUserId },
 *   },
 *   onData: (payload) => {
 *     toast.info(payload.new.title);
 *   },
 * });
 * ```
 *
 * @example Conditional — only subscribe when on bid detail page:
 * ```tsx
 * useRealtimeSubscription({
 *   config: { table: 'bid_submissions', event: 'UPDATE' },
 *   onData: handleBidUpdate,
 *   enabled: isOnBidPage,
 * });
 * ```
 */
export function useRealtimeSubscription<T extends TableName>(
  options: UseRealtimeSubscriptionOptions<T>,
): UseRealtimeSubscriptionReturn {
  const {
    config,
    onData,
    onError,
    onStatusChange,
    enabled = true,
    channelName,
  } = options;

  const [status, setStatus] = useState<RealtimeSubscriptionStatus | null>(null);
  const [channel, setChannel] = useState<RealtimeChannel | null>(null);

  // Use refs for callbacks to avoid re-subscribing when callback references
  // change. This is critical: without refs, every render that creates a new
  // arrow function would tear down and recreate the Realtime channel.
  const onDataRef = useRef(onData);
  const onErrorRef = useRef(onError);
  const onStatusChangeRef = useRef(onStatusChange);

  useEffect(() => { onDataRef.current = onData; }, [onData]);
  useEffect(() => { onErrorRef.current = onError; }, [onError]);
  useEffect(() => { onStatusChangeRef.current = onStatusChange; }, [onStatusChange]);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const { table, event = '*', schema = 'public', filter } = config;

    // Generate a unique channel name if not provided
    const name = channelName ?? `realtime:${schema}:${table}:${event}:${filter?.column ?? 'all'}`;

    // Build the filter string Supabase expects: "column=eq.value"
    const filterString = filter ? `${filter.column}=eq.${filter.value}` : undefined;

    console.log(`[REALTIME] Subscribing to ${name}`);

    const newChannel = supabase
      .channel(name)
      .on(
        'postgres_changes',
        {
          event,
          schema,
          table: table as string,
          ...(filterString ? { filter: filterString } : {}),
        },
        (payload) => {
          const transformed: RealtimePayload<T> = {
            eventType: payload.eventType as 'INSERT' | 'UPDATE' | 'DELETE',
            new: (payload.new ?? {}) as RealtimePayload<T>['new'],
            old: (payload.old ?? {}) as RealtimePayload<T>['old'],
            raw: payload,
          };
          onDataRef.current(transformed);
        },
      )
      .subscribe((subscriptionStatus, err) => {
        console.log(`[REALTIME] ${name} status:`, subscriptionStatus);

        const mappedStatus = subscriptionStatus as RealtimeSubscriptionStatus;
        setStatus(mappedStatus);
        onStatusChangeRef.current?.(mappedStatus);

        if (err) {
          console.error(`[REALTIME] ${name} error:`, err);
          onErrorRef.current?.(new Error(String(err)));
        }
      });

    setChannel(newChannel);

    // Cleanup: unsubscribe and remove channel on unmount or config change
    return () => {
      console.log(`[REALTIME] Unsubscribing from ${name}`);
      supabase.removeChannel(newChannel);
      setChannel(null);
      setStatus(null);
    };
    // Re-subscribe only when serializable config values change (not callback refs).
    // We intentionally list individual config properties instead of the config object
    // to avoid tearing down the channel when a new config reference is passed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    enabled,
    config.table,
    config.event,
    config.schema,
    config.filter?.column,
    config.filter?.value,
    channelName,
  ]);

  return {
    status,
    channel,
    isSubscribed: status === 'SUBSCRIBED',
  };
}
