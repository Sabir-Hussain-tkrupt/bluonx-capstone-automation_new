import { cloneElement, isValidElement, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { cn } from '@/utils/cn';

export interface SidebarItem {
  id: string;
  label: string;
  href: string;
  icon: React.ReactNode;
  badge?: number;
}

export interface SidebarSection {
  title?: string;
  items: SidebarItem[];
}

export interface SidebarUser {
  name: string;
  role: string;
  initials: string;
}

export interface SidebarProps {
  sections: SidebarSection[];
  currentPath: string;
  logo?: React.ReactNode;
  footer?: React.ReactNode;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  /** User shown in the footer pill. If omitted, no user pill is rendered. */
  user?: SidebarUser;
  /**
   * Dropdown panel rendered when the user pill is clicked. Sidebar overrides
   * the panel's `anchor` (top-right vs right-bottom) and `onClose` props at
   * render time based on its own collapsed + open state, so callers can pass
   * placeholder values for those two props.
   */
  userMenu?: React.ReactElement<{ anchor?: string; onClose?: () => void }>;
}

function isActive(currentPath: string, href: string): boolean {
  if (href === '/dashboard') return currentPath === '/dashboard';
  return currentPath.startsWith(href);
}

export function Sidebar({
  sections,
  currentPath,
  logo,
  footer,
  collapsed = false,
  onToggleCollapse,
  user,
  userMenu,
}: SidebarProps) {
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const footerRef = useRef<HTMLDivElement>(null);
  const userTriggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!userMenuOpen) return;

    function handleClickOutside(e: MouseEvent) {
      if (footerRef.current && !footerRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [userMenuOpen]);

  useEffect(() => {
    if (!userMenuOpen) return;

    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setUserMenuOpen(false);
        userTriggerRef.current?.focus();
      }
    }

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [userMenuOpen]);

  const renderUserMenuPanel = () => {
    if (!userMenuOpen || !userMenu || !isValidElement(userMenu)) return null;
    return cloneElement(userMenu, {
      anchor: collapsed ? 'right-bottom' : 'top-right',
      onClose: () => setUserMenuOpen(false),
    });
  };

  return (
    <nav
      aria-label="Main navigation"
      className={cn(
        'relative flex h-full flex-col border-r border-secondary-700 bg-secondary-800 transition-all duration-200',
        collapsed ? 'w-16' : 'w-64',
      )}
    >
      {/* Logo / Brand */}
      <div className="flex h-16 items-center border-b border-secondary-700 px-4">
        {logo ?? (
          <span
            className={cn(
              'font-bold text-white transition-all',
              collapsed ? 'text-lg' : 'text-xl',
            )}
          >
            {collapsed ? 'B' : 'BluOnX'}
          </span>
        )}
      </div>

      {/* Right-edge collapse pill */}
      <button
        type="button"
        onClick={onToggleCollapse}
        aria-expanded={!collapsed}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        className="absolute top-12 -right-[11px] z-50 flex h-[22px] w-[22px] items-center justify-center rounded-full border border-secondary-200 bg-white text-secondary-500 shadow-sm transition-colors hover:bg-secondary-800 hover:text-white"
      >
        <svg
          className={cn('h-3 w-3 transition-transform duration-200', collapsed && 'rotate-180')}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M12.79 5.23a.75.75 0 01-.02 1.06L8.832 10l3.938 3.71a.75.75 0 11-1.04 1.08l-4.5-4.25a.75.75 0 010-1.08l4.5-4.25a.75.75 0 011.06.02z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {/* Navigation sections */}
      <div className="flex-1 overflow-y-auto py-4">
        {sections.map((section, sectionIdx) => (
          <div key={section.title ?? sectionIdx} className={cn(sectionIdx > 0 && 'mt-6')}>
            {section.title && !collapsed && (
              <p className="mb-2 px-4 text-xs font-semibold uppercase tracking-wider text-secondary-500">
                {section.title}
              </p>
            )}
            <ul className="space-y-1 px-2">
              {section.items.map((item) => {
                const active = isActive(currentPath, item.href);
                return (
                  <li key={item.id}>
                    <Link
                      to={item.href}
                      aria-current={active ? 'page' : undefined}
                      title={collapsed ? item.label : undefined}
                      className={cn(
                        'flex items-center gap-3 rounded-lg border-l-2 px-3 py-2 text-sm font-medium transition-colors',
                        active
                          ? 'border-primary-400 bg-primary-600/15 text-white'
                          : 'border-transparent text-secondary-300 hover:bg-secondary-700 hover:text-white',
                        collapsed && 'justify-center',
                      )}
                    >
                      <span className="shrink-0" aria-hidden="true">
                        {item.icon}
                      </span>
                      {!collapsed && (
                        <>
                          <span className="flex-1">{item.label}</span>
                          {item.badge !== undefined && item.badge > 0 && (
                            <span className="inline-flex items-center justify-center rounded-full bg-primary-500 px-2 py-0.5 text-xs font-medium text-white">
                              {item.badge}
                            </span>
                          )}
                        </>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      {/* Footer area */}
      <div ref={footerRef} className="relative border-t border-secondary-700">
        {footer ?? (
          user && (
            <div className={cn(collapsed ? 'flex justify-center px-2 py-3' : 'px-2 py-3')}>
              {collapsed ? (
                <button
                  ref={userTriggerRef}
                  type="button"
                  onClick={() => setUserMenuOpen((o) => !o)}
                  aria-haspopup="menu"
                  aria-expanded={userMenuOpen}
                  aria-label={`User menu, ${user.name}`}
                  className="flex h-7 w-7 items-center justify-center rounded-full bg-primary-600 text-xs font-medium text-white transition-colors hover:bg-secondary-700"
                >
                  {user.initials}
                </button>
              ) : (
                <button
                  ref={userTriggerRef}
                  type="button"
                  onClick={() => setUserMenuOpen((o) => !o)}
                  aria-haspopup="menu"
                  aria-expanded={userMenuOpen}
                  aria-label={`User menu, ${user.name}`}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-2 transition-colors hover:bg-secondary-700"
                >
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary-600 text-xs font-medium text-white">
                    {user.initials}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col text-left">
                    <span className="truncate text-xs font-medium text-white">{user.name}</span>
                    <span className="truncate text-[11px] text-secondary-400">{user.role}</span>
                  </span>
                  <svg
                    className="h-4 w-4 shrink-0 text-secondary-400"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M14.77 12.79a.75.75 0 01-1.06-.02L10 8.832 6.29 12.77a.75.75 0 11-1.08-1.04l4.25-4.5a.75.75 0 011.08 0l4.25 4.5a.75.75 0 01-.02 1.06z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
              )}
              {renderUserMenuPanel()}
            </div>
          )
        )}
      </div>
    </nav>
  );
}
