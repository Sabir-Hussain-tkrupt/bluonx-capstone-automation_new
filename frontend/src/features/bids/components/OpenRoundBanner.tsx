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
      <svg
        className="mt-0.5 h-4 w-4 shrink-0 text-warning-600"
        viewBox="0 0 20 20"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z"
          clipRule="evenodd"
        />
      </svg>
      <p className="leading-snug">
        <span className="font-medium">Round still open — {respondedCount} of {invitedCount} responded.</span>{' '}
        Rankings will shift as more bids arrive.
      </p>
    </div>
  );
}
