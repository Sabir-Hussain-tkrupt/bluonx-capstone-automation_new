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
      icon={
        <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8">
          <path
            d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
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
