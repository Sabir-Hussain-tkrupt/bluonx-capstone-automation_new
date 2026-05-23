import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchNotifications } from '@/features/notifications/api/notifications.queries';

export interface UseNotificationsPageParams {
  unreadOnly: boolean;
  limit: number;
  offset: number;
}

export function useNotificationsPage(params: UseNotificationsPageParams) {
  return useQuery({
    queryKey: queryKeys.notifications.page(params),
    queryFn: () => fetchNotifications(params),
    placeholderData: (prev) => prev,
  });
}
