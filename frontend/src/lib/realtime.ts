import type { RealtimeChannel } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';
import type {
  TableName,
  RealtimeEvent,
  RealtimePayload,
} from '@/types/realtime.types';

/**
 * Subscribe to postgres_changes on a table outside of React.
 *
 * Returns the channel reference for manual cleanup.
 * Caller is responsible for calling `unsubscribeChannel(channel)`
 * when done.
 *
 * For React components, prefer `useRealtimeSubscription` hook instead.
 *
 * @example
 * ```ts
 * const channel = subscribeToTable({
 *   table: 'notifications',
 *   event: 'INSERT',
 *   filter: { column: 'user_id', value: userId },
 *   onData: (payload) => showToast(payload.new.title),
 * });
 *
 * // Later:
 * unsubscribeChannel(channel);
 * ```
 */
export function subscribeToTable<T extends TableName>(params: {
  table: T;
  event?: RealtimeEvent;
  schema?: string;
  filter?: { column: string; value: string };
  channelName?: string;
  onData: (payload: RealtimePayload<T>) => void;
  onError?: (error: Error) => void;
}): RealtimeChannel {
  const {
    table,
    event = '*',
    schema = 'public',
    filter,
    channelName,
    onData,
    onError,
  } = params;

  const name = channelName ?? `realtime:${schema}:${table}:${event}:${filter?.column ?? 'all'}`;
  const filterString = filter ? `${filter.column}=eq.${filter.value}` : undefined;

  const channel = supabase
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
        onData(transformed);
      },
    )
    .subscribe((_status, err) => {
      if (err) {
        console.error(`[REALTIME] ${name} error:`, err);
        onError?.(new Error(String(err)));
      }
    });

  return channel;
}

/**
 * Remove a real-time channel (unsubscribe + cleanup).
 */
export function unsubscribeChannel(channel: RealtimeChannel): void {
  supabase.removeChannel(channel);
}

/**
 * Remove ALL real-time channels.
 * Useful for cleanup on signout or app-level teardown.
 */
export function unsubscribeAllChannels(): void {
  supabase.removeAllChannels();
}
