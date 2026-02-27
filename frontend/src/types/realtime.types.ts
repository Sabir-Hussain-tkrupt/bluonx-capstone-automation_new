import type { RealtimeChannel, RealtimePostgresChangesPayload } from '@supabase/supabase-js';
import type { Database } from '@/types/database.types';

// ─── Table Name Type ─────────────────────────────────────────────────
/**
 * Union of all public table names from the Database type.
 * As database.types.ts gets fully generated, this auto-expands.
 */
export type TableName = keyof Database['public']['Tables'];

// ─── Postgres Change Event Types ─────────────────────────────────────
export type RealtimeEvent = 'INSERT' | 'UPDATE' | 'DELETE' | '*';

// ─── Row type helper ─────────────────────────────────────────────────
/**
 * Extracts the Row type for a given table.
 * Used to type the payload in subscription callbacks.
 */
export type TableRow<T extends TableName> = Database['public']['Tables'][T]['Row'];

// ─── Subscription Configuration ──────────────────────────────────────
export interface RealtimeSubscriptionConfig<T extends TableName> {
  /** Which table to watch. */
  table: T;

  /** Which event(s) to listen for. Defaults to '*' (all). */
  event?: RealtimeEvent;

  /** PostgreSQL schema. Defaults to 'public'. */
  schema?: string;

  /**
   * Column-level equality filter.
   * E.g., `{ column: 'user_id', value: 'uuid-here' }` to only receive
   * changes where user_id matches.
   * Maps to Supabase's `filter` param: `"column=eq.value"`.
   */
  filter?: {
    column: string;
    value: string;
  };
}

// ─── Callback Payload ────────────────────────────────────────────────
export interface RealtimePayload<T extends TableName> {
  /** The event that fired. */
  eventType: 'INSERT' | 'UPDATE' | 'DELETE';
  /** New row data (present for INSERT and UPDATE). */
  new: Partial<TableRow<T>>;
  /** Old row data (present for UPDATE and DELETE). */
  old: Partial<TableRow<T>>;
  /** Raw Supabase payload for advanced use. */
  raw: RealtimePostgresChangesPayload<Record<string, unknown>>;
}

// ─── Subscription Status ─────────────────────────────────────────────
export type RealtimeSubscriptionStatus =
  | 'SUBSCRIBED'
  | 'TIMED_OUT'
  | 'CLOSED'
  | 'CHANNEL_ERROR';

// ─── Hook Options ────────────────────────────────────────────────────
export interface UseRealtimeSubscriptionOptions<T extends TableName> {
  /** Subscription configuration. */
  config: RealtimeSubscriptionConfig<T>;

  /** Callback when a matching change is received. */
  onData: (payload: RealtimePayload<T>) => void;

  /** Optional callback for subscription errors. */
  onError?: (error: Error) => void;

  /** Optional callback when subscription status changes. */
  onStatusChange?: (status: RealtimeSubscriptionStatus) => void;

  /**
   * Whether the subscription is active. Defaults to true.
   * Set to false to conditionally disable (e.g., when user leaves a page).
   */
  enabled?: boolean;

  /**
   * Custom channel name. If not provided, auto-generated from table + event.
   * Useful when you need multiple subscriptions on the same table with
   * different filters.
   */
  channelName?: string;
}

// ─── Hook Return ─────────────────────────────────────────────────────
export interface UseRealtimeSubscriptionReturn {
  /** Current status of the subscription. */
  status: RealtimeSubscriptionStatus | null;
  /** The underlying Supabase channel (for advanced use). */
  channel: RealtimeChannel | null;
  /** Whether the subscription is currently active and receiving events. */
  isSubscribed: boolean;
}
