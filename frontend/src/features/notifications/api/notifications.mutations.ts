import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { Notification } from './notifications.queries';

export interface MarkAllReadResponse {
  updated_count: number;
}

export async function markNotificationRead(id: string): Promise<Notification> {
  const { data } = await api.patch<Notification>(API_ENDPOINTS.NOTIFICATION_READ(id));
  return data;
}

export async function markAllNotificationsRead(): Promise<MarkAllReadResponse> {
  const { data } = await api.patch<MarkAllReadResponse>(
    API_ENDPOINTS.NOTIFICATIONS_MARK_ALL_READ,
  );
  return data;
}
