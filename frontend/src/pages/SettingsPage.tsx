import { Link } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';

interface SettingsCardProps {
  to?: string;
  title: string;
  description: string;
  icon: React.ReactNode;
  comingSoon?: boolean;
}

function SettingsCard({ to, title, description, icon, comingSoon }: SettingsCardProps) {
  const content = (
    <div
      className={`group flex items-start gap-4 rounded-lg border border-secondary-200 bg-white p-5 shadow-sm transition ${
        comingSoon
          ? 'cursor-not-allowed opacity-60'
          : 'hover:border-primary-400 hover:shadow-md'
      }`}
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
        <svg
          className="mt-1 h-5 w-5 shrink-0 text-secondary-300 transition group-hover:text-primary-500"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M7.21 14.77a.75.75 0 010-1.06L10.94 10 7.21 6.29a.75.75 0 111.08-1.04l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.08-.04z"
            clipRule="evenodd"
          />
        </svg>
      )}
    </div>
  );

  if (comingSoon || !to) {
    return <div aria-disabled="true">{content}</div>;
  }
  return <Link to={to}>{content}</Link>;
}

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-secondary-900">Settings</h1>
        <p className="mt-1 text-sm text-secondary-500">
          Administer shared configuration for BluOnX.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <SettingsCard
          to={ROUTES.SETTINGS_TRADES}
          title="Manage Trades"
          description="View trades grouped by project phase and add new scope categories."
          icon={<TradesIcon />}
        />
        <SettingsCard
          comingSoon
          title="User Management"
          description="Invite team members and manage admin / project manager roles."
          icon={<UsersIcon />}
        />
      </div>
    </div>
  );
}

function TradesIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M3 4a1 1 0 011-1h3a1 1 0 011 1v3a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM3 12a1 1 0 011-1h3a1 1 0 011 1v3a1 1 0 01-1 1H4a1 1 0 01-1-1v-3zM12 4a1 1 0 011-1h3a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1V4zM12 12a1 1 0 011-1h3a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-3z" />
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M10 9a3 3 0 100-6 3 3 0 000 6zM6 8a2 2 0 11-4 0 2 2 0 014 0zM1.49 15.326a.78.78 0 01-.358-.442 3 3 0 014.308-3.516 6.484 6.484 0 00-1.905 3.959c-.023.222-.014.442.025.654a4.97 4.97 0 01-2.07-.655zM16.44 15.98a4.97 4.97 0 002.07-.654.78.78 0 00.357-.442 3 3 0 00-4.308-3.517 6.484 6.484 0 011.907 3.96 2.32 2.32 0 01-.026.654zM18 8a2 2 0 11-4 0 2 2 0 014 0zM5.304 16.19a.844.844 0 01-.277-.71 5 5 0 019.947 0 .843.843 0 01-.277.71A6.975 6.975 0 0110 18a6.974 6.974 0 01-4.696-1.81z" />
    </svg>
  );
}
