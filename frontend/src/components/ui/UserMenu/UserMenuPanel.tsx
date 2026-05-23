import { useCallback, useEffect, useRef } from 'react';
import { cn } from '@/utils/cn';
import type { UserMenuItem } from './UserMenu';

export type UserMenuAnchor = 'top-right' | 'bottom-right' | 'right-bottom';

export interface UserMenuPanelProps {
  /** Full name shown in the panel header. */
  userName: string;
  /** Email shown under the name in the panel header. */
  userEmail: string;
  /** Optional caller-supplied menu items rendered above Sign Out. */
  menuItems?: UserMenuItem[];
  /** Invoked when the Sign Out item is activated. */
  onSignOut: () => void;
  /**
   * Where the panel sits relative to its trigger.
   * - `bottom-right`: opens down and to the right (top-bar trigger).
   * - `top-right`: opens upward and right-aligned (sidebar expanded footer).
   * - `right-bottom`: opens to the right, bottom-aligned (sidebar collapsed footer).
   */
  anchor: UserMenuAnchor;
  /** Caller-provided close hook; invoked after any item activation. */
  onClose: () => void;
}

const anchorClasses: Record<UserMenuAnchor, string> = {
  'bottom-right': 'right-0 top-full mt-2 origin-top-right',
  'top-right': 'right-0 bottom-full mb-2 origin-bottom-right',
  'right-bottom': 'left-full bottom-0 ml-2 origin-bottom-left',
};

export function UserMenuPanel({
  userName,
  userEmail,
  menuItems = [],
  onSignOut,
  anchor,
  onClose,
}: UserMenuPanelProps) {
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

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

  useEffect(() => {
    itemRefs.current[0]?.focus();
  }, []);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
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
  }, []);

  return (
    <div
      role="menu"
      aria-label="User menu"
      onKeyDown={handleKeyDown}
      className={cn(
        'absolute z-50 w-56 rounded-lg border border-secondary-200 bg-white py-1 shadow-lg',
        anchorClasses[anchor],
      )}
    >
      <div className="border-b border-secondary-100 px-4 py-3">
        <p className="text-sm font-medium text-secondary-900">{userName}</p>
        <p className="text-xs text-secondary-500">{userEmail}</p>
      </div>

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
                onClose();
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
  );
}
