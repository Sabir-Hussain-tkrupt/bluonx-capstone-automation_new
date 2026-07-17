import { PortalErrorPage } from './PortalErrorPage';

/**
 * Page B — the check-in is no longer current: its milestone was rescheduled
 * (cycle bumped, stranding this link), completed, or cancelled, or the link
 * expired. Neutral and reassuring; nothing for the vendor to do.
 */
export function MilestoneNoLongerCurrentPage() {
  return (
    <PortalErrorPage
      variant="warning"
      title="This check-in is no longer current"
      message="The schedule for this milestone has changed since this link was sent, so no response is needed. If you have a question, please contact the BluOnX project manager who sent it."
      icon={
        <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8">
          <path
            d="M12 8v4l3 2m6-2a9 9 0 11-18 0 9 9 0 0118 0z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      }
    />
  );
}
