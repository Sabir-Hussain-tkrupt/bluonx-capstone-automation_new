import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { ROUTES } from '@/constants/routes';
import { TradeManagementPanel } from '../components/TradeManagementPanel';

export function TradesSettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <Link
          to={ROUTES.SETTINGS}
          className="inline-flex items-center gap-1 text-sm text-secondary-500 hover:text-secondary-700"
        >
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          Back to Settings
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-secondary-900">Manage Trades</h1>
        <p className="mt-1 text-sm text-secondary-500">
          View trades grouped by project phase and add new ones. Editing and
          deactivating trades is intentionally disabled to protect existing
          tasks, bid packages, and vendor associations.
        </p>
      </div>

      <TradeManagementPanel />
    </div>
  );
}
