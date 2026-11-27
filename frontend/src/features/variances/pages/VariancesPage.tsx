import { VarianceList } from '../components/VarianceList';

/** Variances across every project (sidebar). */
export function VariancesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-secondary-900">Variances</h1>
        <p className="mt-1 text-sm text-secondary-500">
          Field variances funded from contingency, with their own approval and payment status.
        </p>
      </div>
      <VarianceList />
    </div>
  );
}
