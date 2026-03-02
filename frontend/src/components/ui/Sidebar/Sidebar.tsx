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

export interface SidebarProps {
  sections: SidebarSection[];
  currentPath: string;
  logo?: React.ReactNode;
  footer?: React.ReactNode;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
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
}: SidebarProps) {
  return (
    <nav
      aria-label="Main navigation"
      className={cn(
        'flex h-full flex-col border-r border-secondary-200 bg-white transition-all duration-200',
        collapsed ? 'w-16' : 'w-64',
      )}
    >
      {/* Logo / Brand */}
      <div className="flex h-16 items-center border-b border-secondary-200 px-4">
        {logo ?? (
          <span
            className={cn(
              'font-bold text-primary-600 transition-all',
              collapsed ? 'text-lg' : 'text-xl',
            )}
          >
            {collapsed ? 'B' : 'BluOnX'}
          </span>
        )}
      </div>

      {/* Navigation sections */}
      <div className="flex-1 overflow-y-auto py-4">
        {sections.map((section, sectionIdx) => (
          <div key={section.title ?? sectionIdx} className={cn(sectionIdx > 0 && 'mt-6')}>
            {section.title && !collapsed && (
              <p className="mb-2 px-4 text-xs font-semibold uppercase tracking-wider text-secondary-400">
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
                        'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
                        active
                          ? 'bg-primary-50 text-primary-700'
                          : 'text-secondary-600 hover:bg-secondary-50 hover:text-secondary-900',
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
                            <span className="inline-flex items-center justify-center rounded-full bg-primary-100 px-2 py-0.5 text-xs font-medium text-primary-700">
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
      <div className="border-t border-secondary-200 p-2">
        {footer ?? (
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-expanded={!collapsed}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="flex w-full items-center justify-center rounded-lg p-2 text-secondary-400 hover:bg-secondary-50 hover:text-secondary-600"
          >
            <svg
              className={cn('h-5 w-5 transition-transform', collapsed && 'rotate-180')}
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
        )}
      </div>
    </nav>
  );
}
