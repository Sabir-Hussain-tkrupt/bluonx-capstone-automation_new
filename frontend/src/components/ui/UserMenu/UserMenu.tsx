import { useEffect, useRef, useState } from 'react';
import { UserMenuPanel } from './UserMenuPanel';
import { getInitials } from './getInitials';

export interface UserMenuItem {
  label: string;
  onClick: () => void;
  icon?: React.ReactNode;
}

export interface UserMenuProps {
  userName: string;
  userEmail: string;
  userRole: string;
  avatarUrl?: string;
  menuItems?: UserMenuItem[];
  onSignOut: () => void;
}

export function UserMenu({
  userName,
  userEmail,
  userRole,
  avatarUrl,
  menuItems = [],
  onSignOut,
}: UserMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
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
    <div className="relative" ref={menuRef}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={isOpen}
        className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-secondary-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
      >
        {avatarUrl ? (
          <img
            src={avatarUrl}
            alt={userName}
            className="h-8 w-8 rounded-full object-cover"
          />
        ) : (
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary-100 text-xs font-semibold text-primary-700">
            {getInitials(userName)}
          </span>
        )}
        <span className="hidden text-left md:block">
          <span className="block text-sm font-medium text-secondary-900">{userName}</span>
          <span className="block text-xs text-secondary-500">{userRole}</span>
        </span>
        <svg className="hidden h-4 w-4 text-secondary-400 md:block" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </button>

      {isOpen && (
        <UserMenuPanel
          userName={userName}
          userEmail={userEmail}
          menuItems={menuItems}
          onSignOut={onSignOut}
          anchor="bottom-right"
          onClose={() => setIsOpen(false)}
        />
      )}
    </div>
  );
}
