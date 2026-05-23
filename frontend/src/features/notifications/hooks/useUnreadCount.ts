import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchUnreadCount } from '@/features/notifications/api/notifications.queries';

const UNREAD_POLL_MS = 60_000;

export function useUnreadCount() {
  return useQuery({
    queryKey: queryKeys.notifications.unreadCount(),
    queryFn: fetchUnreadCount,
    refetchInterval: UNREAD_POLL_MS,
    refetchOnWindowFocus: true,
  });
}
