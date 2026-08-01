import { Menu } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface TopHeaderProps {
  title?: string;
  breadcrumbs?: React.ReactNode;
  actions?: React.ReactNode;
  notificationBell?: React.ReactNode;
  userMenu?: React.ReactNode;
  onMenuToggle?: () => void;
  className?: string;
}

export function TopHeader({
  title,
  breadcrumbs,
  actions,
  notificationBell,
  userMenu,
  onMenuToggle,
  className,
}: TopHeaderProps) {
  return (
    <header
      className={cn(
        'flex items-center justify-between border-b border-secondary-200 bg-white px-6 py-3',
        className,
      )}
    >
      {/* Left side. min-w-0 all the way down, so a long breadcrumb trail
          scrolls inside its own box instead of pushing the right side off. */}
      <div className="flex min-w-0 items-center gap-4">
        {/* Mobile hamburger */}
        {onMenuToggle && (
          <button
            type="button"
            onClick={onMenuToggle}
            className="rounded-lg p-1.5 text-secondary-400 hover:bg-secondary-50 hover:text-secondary-600 lg:hidden"
            aria-label="Open navigation menu"
          >
            <Menu className="h-6 w-6" aria-hidden="true" />
          </button>
        )}
        <div className="min-w-0">
          {breadcrumbs}
          {title && (
            <h1 className={cn('font-semibold text-secondary-900', breadcrumbs ? 'mt-0.5 text-lg' : 'text-xl')}>
              {title}
            </h1>
          )}
        </div>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        {actions}
        {notificationBell}
        {userMenu}
      </div>
    </header>
  );
}
