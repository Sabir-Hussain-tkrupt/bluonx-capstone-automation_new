interface CancelledPackageNoticeProps {
  /** ISO timestamp from bid_packages.cancelled_at. */
  cancelledAt: string | null;
  /** Null when the user row is gone (soft-deleted, or the FK nulled). */
  cancelledByName: string | null;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/**
 * Explains a voided round on the bid package detail page.
 *
 * Every action is hidden on a cancelled package, so without this the page looks
 * inert for no stated reason. Renders nothing unless there is a date to show —
 * the name is optional and degrades to "Cancelled on <date>".
 */
export function CancelledPackageNotice({
  cancelledAt,
  cancelledByName,
}: CancelledPackageNoticeProps) {
  if (!cancelledAt) return null;

  return (
    <div
      role="status"
      className="rounded-md border border-danger-200 bg-danger-50 px-4 py-3 text-sm text-danger-800"
    >
      <span className="font-medium">This bid round was cancelled</span>
      {cancelledByName ? ` by ${cancelledByName}` : ''} on{' '}
      {formatDate(cancelledAt)}. Submitted bids are kept for reference but can no
      longer be awarded. Start a new round to re-bid this task.
    </div>
  );
}
