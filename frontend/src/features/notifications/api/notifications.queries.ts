import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';

export interface Notification {
  id: string;
  user_id: string;
  title: string;
  message: string | null;
  notification_type:
    | 'insurance_expiring'
    | 'insurance_expired'
    | 'post_deadline_non_responders'
    | 'scheduler_alert'
    | 'milestone_delayed'
    | 'milestone_unresponsive'
    | 'milestone_completed';
  reference_type: string | null;
  reference_id: string | null;
  is_read: boolean;
  created_at: string;
  deep_link_path: string | null;
}

export interface UnreadCountResponse {
  count: number;
}

export interface NotificationsListParams {
  unreadOnly?: boolean;
  limit?: number;
  offset?: number;
}

export async function fetchNotifications(
  params: NotificationsListParams = {},
): Promise<Notification[]> {
  const { data } = await api.get<Notification[]>(API_ENDPOINTS.NOTIFICATIONS, {
    params: {
      unread_only: params.unreadOnly ?? false,
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    },
  });
  return data;
}

export async function fetchUnreadCount(): Promise<UnreadCountResponse> {
  const { data } = await api.get<UnreadCountResponse>(
    API_ENDPOINTS.NOTIFICATIONS_UNREAD_COUNT,
  );
  return data;
}
