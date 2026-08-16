import { CalendarDays, FileSignature, LayoutGrid, Users } from 'lucide-react';
import { SettingsCard } from '@/components/ui/SettingsCard';
import { ROUTES } from '@/constants/routes';

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
          icon={<LayoutGrid className="h-5 w-5" aria-hidden="true" />}
        />
        <SettingsCard
          to={ROUTES.SETTINGS_CALENDAR}
          title="Holiday Calendar"
          description="Manage org-wide holidays that extend vendor response deadlines."
          icon={<CalendarDays className="h-5 w-5" aria-hidden="true" />}
        />
        <SettingsCard
          to={ROUTES.SETTINGS_USERS}
          title="User Management"
          description="Invite team members and manage admin / project manager roles."
          icon={<Users className="h-5 w-5" aria-hidden="true" />}
        />
        <SettingsCard
          to={ROUTES.SETTINGS_CONTRACT_SIGNERS}
          title="Contract Signers"
          description="Manage the people authorized to sign contracts on behalf of BluOnX."
          icon={<FileSignature className="h-5 w-5" aria-hidden="true" />}
        />
      </div>
    </div>
  );
}
