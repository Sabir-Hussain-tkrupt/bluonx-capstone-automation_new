import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  fetchNotifications,
  type NotificationsListParams,
} from '@/features/notifications/api/notifications.queries';

export function useNotifications(params: NotificationsListParams = {}) {
  return useQuery({
    queryKey: queryKeys.notifications.list({
      unreadOnly: params.unreadOnly,
      limit: params.limit,
    }),
    queryFn: () => fetchNotifications(params),
  });
}
