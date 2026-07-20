import { Link } from 'react-router-dom';
import { ChevronRight, LayoutGrid, Users } from 'lucide-react';
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
  return <LayoutGrid className="h-5 w-5" aria-hidden="true" />;
}

function UsersIcon() {
  return <Users className="h-5 w-5" aria-hidden="true" />;
}
