import { useEffect, useRef, useState } from 'react';
import { Bell } from 'lucide-react';
import { useUnreadCount } from '@/features/notifications/hooks/useUnreadCount';
import { NotificationDropdown } from './NotificationDropdown';

function formatBadgeCount(n: number): string {
  if (n > 99) return '99+';
  return String(n);
}

export function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const { data } = useUnreadCount();
  const count = data?.count ?? 0;

  useEffect(() => {
    if (!isOpen) return;
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setIsOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen]);

  return (
    <div className="relative" ref={wrapperRef}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={isOpen}
        aria-label={count > 0 ? `Notifications (${count} unread)` : 'Notifications'}
        className="relative cursor-pointer rounded-lg p-1.5 text-secondary-400 hover:bg-secondary-50 hover:text-secondary-600 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
      >
        <Bell className="h-6 w-6" aria-hidden="true" />
        {count > 0 && (
          <span
            data-testid="notification-badge"
            className="absolute -right-0.5 -top-0.5 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-danger-500 px-1 text-[10px] font-semibold leading-4 text-white"
          >
            {formatBadgeCount(count)}
          </span>
        )}
      </button>

      {isOpen && <NotificationDropdown onClose={() => setIsOpen(false)} />}
    </div>
  );
}
