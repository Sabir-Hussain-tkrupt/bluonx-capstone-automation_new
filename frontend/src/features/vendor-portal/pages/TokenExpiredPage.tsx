import { Clock } from 'lucide-react';
import { PortalErrorPage } from './PortalErrorPage';

/**
 * Shared expiry page for BOTH portal surfaces — reached on a 410 expired magic
 * link and on a mid-session 401 (the vendor JWT lapses after ~4h). Copy is kept
 * neutral so it reads correctly for a bid or a milestone session, and for both
 * the "re-open the link" (session lapsed) and "contact your PM" (link no longer
 * valid) sub-cases.
 */
export function TokenExpiredPage() {
  return (
    <PortalErrorPage
      variant="warning"
      title="This link has expired"
      message="For your security, secure links expire after a period of time. Please re-open the most recent link from your email, or contact the BluOnX project manager who sent it if you still need access."
      icon={<Clock className="h-8 w-8" aria-hidden="true" />}
    />
  );
}
