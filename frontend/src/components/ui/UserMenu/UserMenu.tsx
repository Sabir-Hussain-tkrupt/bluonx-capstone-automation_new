import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/utils/cn';

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

function getInitials(name: string): string {
  return name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
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
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // All interactive items: custom items + sign out
  const allItems: UserMenuItem[] = [
    ...menuItems,
    {
      label: 'Sign out',
      onClick: onSignOut,
      icon: (
        <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path fillRule="evenodd" d="M3 4.25A2.25 2.25 0 015.25 2h5.5A2.25 2.25 0 0113 4.25v2a.75.75 0 01-1.5 0v-2a.75.75 0 00-.75-.75h-5.5a.75.75 0 00-.75.75v11.5c0 .414.336.75.75.75h5.5a.75.75 0 00.75-.75v-2a.75.75 0 011.5 0v2A2.25 2.25 0 0110.75 18h-5.5A2.25 2.25 0 013 15.75V4.25z" clipRule="evenodd" />
          <path fillRule="evenodd" d="M19 10a.75.75 0 00-.75-.75H8.704l1.048-.943a.75.75 0 10-1.004-1.114l-2.5 2.25a.75.75 0 000 1.114l2.5 2.25a.75.75 0 101.004-1.114l-1.048-.943h9.546A.75.75 0 0019 10z" clipRule="evenodd" />
        </svg>
      ),
    },
  ];

  // Close on click outside
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

  // Close on Escape
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

  // Arrow key navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const items = itemRefs.current.filter(Boolean) as HTMLButtonElement[];
      const currentIdx = items.indexOf(document.activeElement as HTMLButtonElement);

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const next = currentIdx < items.length - 1 ? currentIdx + 1 : 0;
        items[next]?.focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prev = currentIdx > 0 ? currentIdx - 1 : items.length - 1;
        items[prev]?.focus();
      }
    },
    [],
  );

  return (
    <div className="relative" ref={menuRef}>
      {/* Trigger */}
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen((o) => !o)}
        aria-haspopup="true"
        aria-expanded={isOpen}
        className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-secondary-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
      >
        {/* Avatar */}
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

      {/* Dropdown */}
      {isOpen && (
        <div
          role="menu"
          aria-label="User menu"
          onKeyDown={handleKeyDown}
          className="absolute right-0 top-full z-50 mt-2 w-56 origin-top-right rounded-lg border border-secondary-200 bg-white py-1 shadow-lg"
        >
          {/* User info header */}
          <div className="border-b border-secondary-100 px-4 py-3">
            <p className="text-sm font-medium text-secondary-900">{userName}</p>
            <p className="text-xs text-secondary-500">{userEmail}</p>
          </div>

          {/* Menu items */}
          {allItems.map((item, idx) => {
            const isSignOut = idx === allItems.length - 1;
            return (
              <div key={item.label}>
                {isSignOut && menuItems.length > 0 && (
                  <div className="my-1 border-t border-secondary-100" />
                )}
                <button
                  ref={(el) => {
                    itemRefs.current[idx] = el;
                  }}
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    item.onClick();
                    setIsOpen(false);
                  }}
                  className={cn(
                    'flex w-full items-center gap-2 px-4 py-2 text-sm transition-colors',
                    'hover:bg-secondary-50 focus-visible:bg-secondary-50 focus-visible:outline-none',
                    isSignOut
                      ? 'text-danger-600 hover:text-danger-700'
                      : 'text-secondary-700 hover:text-secondary-900',
                  )}
                >
                  {item.icon && <span className="shrink-0">{item.icon}</span>}
                  {item.label}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
