import { AlertTriangle } from 'lucide-react';

export interface OpenRoundBannerProps {
  respondedCount: number;
  invitedCount: number;
}

/**
 * Non-blocking notice shown when the round is still open and pending vendors
 * exist. Task 8.3 acceptance: "Round still open — N of M responded. Rankings
 * shift as bids arrive."
 */
export function OpenRoundBanner({
  respondedCount,
  invitedCount,
}: OpenRoundBannerProps) {
  return (
    <div
      role="status"
      className="flex items-start gap-3 rounded-lg border border-warning-200 bg-warning-50 px-4 py-3 text-sm text-warning-800"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning-600" aria-hidden="true" />
      <p className="leading-snug">
        <span className="font-medium">Round still open — {respondedCount} of {invitedCount} responded.</span>{' '}
        Rankings will shift as more bids arrive.
      </p>
    </div>
  );
}
