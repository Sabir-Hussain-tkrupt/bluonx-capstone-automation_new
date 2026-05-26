import { useInsuranceExpiringCount } from '@/features/vendors/hooks/useInsuranceExpiringCount';

/**
 * Amber badge that surfaces the count of vendors with insurance expiring
 * within 30 days (or already lapsed). Hidden when the count is 0 or the
 * query is loading/errored. Polls every 60s — matches the notification
 * unread-count cadence.
 */
export function InsuranceExpiringBadge() {
  const { data, isLoading, isError } = useInsuranceExpiringCount();

  if (isLoading || isError) return null;
  const count = data?.count ?? 0;
  if (count <= 0) return null;

  return (
    <span
      data-testid="insurance-expiring-badge"
      className="bg-warning-100 text-warning-700 px-2 py-0.5 rounded-full text-xs font-medium"
    >
      {count} insurance alert{count === 1 ? '' : 's'}
    </span>
  );
}
