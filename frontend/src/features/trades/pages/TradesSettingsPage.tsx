import { TradeManagementPanel } from '../components/TradeManagementPanel';

export function TradesSettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-secondary-900">Manage Trades</h1>
        <p className="mt-1 text-sm text-secondary-500">
          Trades grouped by project phase, each with optional subtrades. A trade or
          subtrade can be renamed or deleted only while no task, vendor or template
          uses it.
        </p>
      </div>

      <TradeManagementPanel />
    </div>
  );
}
