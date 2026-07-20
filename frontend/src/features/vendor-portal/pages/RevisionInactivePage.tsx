import { AlertTriangle } from 'lucide-react';
import { PortalErrorPage } from './PortalErrorPage';

/**
 * Shown when a revision request was cancelled or expired between the
 * vendor opening the email and submitting (submit → 410), or when the
 * prefill endpoint rejects (403/404). The original bid is untouched.
 */
export function RevisionInactivePage() {
  return (
    <PortalErrorPage
      variant="warning"
      title="This revision request is no longer active"
      message="Your original bid remains in consideration. If you believe this is a mistake, please contact the BluOnX project manager who requested the revision."
      icon={<AlertTriangle className="h-8 w-8" aria-hidden="true" />}
    />
  );
}
