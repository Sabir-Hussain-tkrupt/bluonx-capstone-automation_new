import { Link } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';
import { useNotifications } from '@/features/notifications/hooks/useNotifications';
import { NotificationItem } from './NotificationItem';

const DROPDOWN_LIMIT = 15;
const MAX_UNREAD = 10;
const MAX_READ_CONTEXT = 5;

export interface NotificationDropdownProps {
  onClose: () => void;
}

export function NotificationDropdown({ onClose }: NotificationDropdownProps) {
  const { data, isLoading, isError } = useNotifications({ limit: DROPDOWN_LIMIT });

  const items = data ?? [];
  const unread = items.filter((n) => !n.is_read).slice(0, MAX_UNREAD);
  const read = items.filter((n) => n.is_read).slice(0, MAX_READ_CONTEXT);
  const displayed = [...unread, ...read];

  return (
    <div
      role="menu"
      aria-label="Notifications"
      className="absolute right-0 top-full z-50 mt-2 w-96 origin-top-right overflow-hidden rounded-lg border border-secondary-200 bg-white shadow-lg"
    >
      <div className="border-b border-secondary-100 px-4 py-2.5">
        <p className="text-sm font-semibold text-secondary-900">Notifications</p>
      </div>

      <div className="max-h-96 overflow-y-auto">
        {isLoading && (
          <p className="px-4 py-6 text-center text-sm text-secondary-500">
            Loading…
          </p>
        )}
        {isError && (
          <p className="px-4 py-6 text-center text-sm text-danger-600">
            Failed to load notifications.
          </p>
        )}
        {!isLoading && !isError && displayed.length === 0 && (
          <p className="px-4 py-6 text-center text-sm text-secondary-500">
            No notifications yet.
          </p>
        )}
        {!isLoading && !isError && displayed.length > 0 && (
          <ul className="divide-y divide-secondary-100">
            {displayed.map((n) => (
              <li key={n.id}>
                <NotificationItem notification={n} onActivate={onClose} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-secondary-100 bg-secondary-50 px-4 py-2">
        <Link
          to={ROUTES.NOTIFICATIONS}
          onClick={onClose}
          className="block text-center text-sm font-medium text-primary-600 hover:text-primary-700"
        >
          View all
        </Link>
      </div>
    </div>
  );
}
