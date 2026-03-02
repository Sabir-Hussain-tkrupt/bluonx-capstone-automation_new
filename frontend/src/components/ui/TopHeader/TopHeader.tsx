import { cn } from '@/utils/cn';

export interface TopHeaderProps {
  title?: string;
  breadcrumbs?: React.ReactNode;
  actions?: React.ReactNode;
  userMenu?: React.ReactNode;
  onMenuToggle?: () => void;
  className?: string;
}

export function TopHeader({
  title,
  breadcrumbs,
  actions,
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
      {/* Left side */}
      <div className="flex items-center gap-4">
        {/* Mobile hamburger */}
        {onMenuToggle && (
          <button
            type="button"
            onClick={onMenuToggle}
            className="rounded-lg p-1.5 text-secondary-400 hover:bg-secondary-50 hover:text-secondary-600 lg:hidden"
            aria-label="Open navigation menu"
          >
            <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            </svg>
          </button>
        )}
        <div>
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
        {userMenu}
      </div>
    </header>
  );
}
