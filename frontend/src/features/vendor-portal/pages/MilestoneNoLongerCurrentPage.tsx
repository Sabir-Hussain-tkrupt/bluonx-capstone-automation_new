import { Clock } from 'lucide-react';
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
      icon={<Clock className="h-8 w-8" aria-hidden="true" />}
    />
  );
}
