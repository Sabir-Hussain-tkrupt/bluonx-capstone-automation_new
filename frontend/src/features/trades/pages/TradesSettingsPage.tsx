import { Link } from 'react-router-dom';
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
          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path
              fillRule="evenodd"
              d="M12.79 5.23a.75.75 0 010 1.06L9.06 10l3.73 3.71a.75.75 0 11-1.06 1.06l-4.25-4.24a.75.75 0 010-1.06l4.25-4.24a.75.75 0 011.06 0z"
              clipRule="evenodd"
            />
          </svg>
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
