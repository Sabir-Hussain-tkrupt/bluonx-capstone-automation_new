import { useState } from 'react';
import { cn } from '@/utils/cn';
import { useNotificationsPage } from '@/features/notifications/hooks/useNotificationsPage';
import { useMarkAllAsRead } from '@/features/notifications/hooks/useMarkAllAsRead';
import { NotificationItem } from '@/features/notifications/components/NotificationItem';

const PAGE_SIZE = 50;

export function NotificationsPage() {
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [offset, setOffset] = useState(0);

  const { data, isLoading, isError, isFetching } = useNotificationsPage({
    unreadOnly,
    limit: PAGE_SIZE,
    offset,
  });
  const markAllAsRead = useMarkAllAsRead();

  const items = data ?? [];
  const hasNext = items.length === PAGE_SIZE;
  const page = Math.floor(offset / PAGE_SIZE) + 1;

  const setFilter = (next: boolean) => {
    setUnreadOnly(next);
    setOffset(0);
  };

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-secondary-900">Notifications</h1>
        <button
          type="button"
          onClick={() => markAllAsRead.mutate()}
          disabled={markAllAsRead.isPending}
          className="rounded-lg border border-secondary-200 bg-white px-3 py-1.5 text-sm font-medium text-secondary-700 hover:bg-secondary-50 disabled:opacity-50"
        >
          {markAllAsRead.isPending ? 'Marking…' : 'Mark all as read'}
        </button>
      </div>

      <div className="mb-4 inline-flex rounded-lg border border-secondary-200 bg-white p-1">
        <button
          type="button"
          onClick={() => setFilter(false)}
          className={cn(
            'rounded px-3 py-1 text-sm font-medium',
            !unreadOnly ? 'bg-primary-100 text-primary-700' : 'text-secondary-600',
          )}
        >
          All
        </button>
        <button
          type="button"
          onClick={() => setFilter(true)}
          className={cn(
            'rounded px-3 py-1 text-sm font-medium',
            unreadOnly ? 'bg-primary-100 text-primary-700' : 'text-secondary-600',
          )}
        >
          Unread only
        </button>
      </div>

      <div className="overflow-hidden rounded-lg border border-secondary-200 bg-white">
        {isLoading && (
          <p className="px-4 py-12 text-center text-sm text-secondary-500">Loading…</p>
        )}
        {isError && (
          <p className="px-4 py-12 text-center text-sm text-danger-600">
            Failed to load notifications.
          </p>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <p className="px-4 py-12 text-center text-sm text-secondary-500">
            {unreadOnly ? 'No unread notifications.' : 'No notifications yet.'}
          </p>
        )}
        {!isLoading && !isError && items.length > 0 && (
          <ul className="divide-y divide-secondary-100">
            {items.map((n) => (
              <li key={n.id}>
                <NotificationItem notification={n} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between text-sm">
        <span className="text-secondary-500">
          Page {page}
          {isFetching && ' · refreshing…'}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            disabled={offset === 0}
            className="rounded-lg border border-secondary-200 bg-white px-3 py-1.5 font-medium text-secondary-700 hover:bg-secondary-50 disabled:opacity-50"
          >
            Previous
          </button>
          <button
            type="button"
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
            disabled={!hasNext}
            className="rounded-lg border border-secondary-200 bg-white px-3 py-1.5 font-medium text-secondary-700 hover:bg-secondary-50 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
