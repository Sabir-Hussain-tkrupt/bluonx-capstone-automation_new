import { useNavigate } from 'react-router-dom';
import { cn } from '@/utils/cn';
import { useMarkAsRead } from '@/features/notifications/hooks/useMarkAsRead';
import { formatRelativeTime } from '@/features/notifications/utils/formatRelativeTime';
import type { Notification } from '@/features/notifications/api/notifications.queries';

export interface NotificationItemProps {
  notification: Notification;
  onActivate?: () => void;
}

export function NotificationItem({ notification, onActivate }: NotificationItemProps) {
  const navigate = useNavigate();
  const markAsRead = useMarkAsRead();

  const isUnread = !notification.is_read;
  const canNavigate = Boolean(notification.deep_link_path);

  const handleClick = () => {
    if (isUnread) {
      markAsRead.mutate(notification.id);
    }
    if (notification.deep_link_path) {
      navigate(notification.deep_link_path);
    }
    onActivate?.();
  };

  const handleMarkRead = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isUnread) {
      markAsRead.mutate(notification.id);
    }
  };

  return (
    <div
      role={canNavigate ? 'button' : undefined}
      tabIndex={canNavigate ? 0 : undefined}
      onClick={canNavigate ? handleClick : undefined}
      onKeyDown={
        canNavigate
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handleClick();
              }
            }
          : undefined
      }
      className={cn(
        'flex items-start gap-3 px-4 py-3 transition-colors',
        canNavigate && 'cursor-pointer hover:bg-secondary-50',
        isUnread ? 'border-l-2 border-primary-500 bg-primary-50/30' : 'border-l-2 border-transparent',
      )}
    >
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            'text-sm leading-snug',
            isUnread ? 'font-semibold text-secondary-900' : 'text-secondary-700',
          )}
        >
          {notification.title}
        </p>
        {notification.message && (
          <p className="mt-0.5 line-clamp-2 text-xs text-secondary-600">
            {notification.message}
          </p>
        )}
        <p className="mt-1 text-xs text-secondary-400">
          {formatRelativeTime(notification.created_at)}
        </p>
      </div>
      {isUnread && (
        <button
          type="button"
          onClick={handleMarkRead}
          disabled={markAsRead.isPending}
          className="shrink-0 rounded px-2 py-1 text-xs font-medium text-primary-600 hover:bg-primary-100 hover:text-primary-700 disabled:opacity-50"
        >
          Mark read
        </button>
      )}
    </div>
  );
}
