import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/utils/cn';

export interface SettingsCardProps {
  /** Destination route. Omit (or set `comingSoon`) to render a non-interactive card. */
  to?: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  /** Renders the card dimmed with a "Coming soon" pill and no click-through. */
  comingSoon?: boolean;
}

/**
 * A settings hub tile: icon, title, description, and click-through to a detail
 * route. Renders as a `Link` when actionable, or an inert `div` when
 * `comingSoon` or `to` is absent.
 */
export function SettingsCard({ to, title, description, icon, comingSoon }: SettingsCardProps) {
  const content = (
    <div
      className={cn(
        'group flex items-start gap-4 rounded-lg border border-secondary-300 bg-white p-5 shadow-md ring-1 ring-secondary-900/5 transition',
        comingSoon
          ? 'cursor-not-allowed opacity-60'
          : 'hover:-translate-y-0.5 hover:border-primary-400 hover:shadow-lg',
      )}
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-600">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold text-secondary-900">{title}</h3>
          {comingSoon && (
            <span className="rounded-full bg-secondary-100 px-2 py-0.5 text-xs font-medium text-secondary-600">
              Coming soon
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-secondary-500">{description}</p>
      </div>
      {!comingSoon && (
        <ChevronRight
          className="mt-1 h-5 w-5 shrink-0 text-secondary-300 transition group-hover:text-primary-500"
          aria-hidden="true"
        />
      )}
    </div>
  );

  if (comingSoon || !to) {
    return <div aria-disabled="true">{content}</div>;
  }
  return <Link to={to}>{content}</Link>;
}
