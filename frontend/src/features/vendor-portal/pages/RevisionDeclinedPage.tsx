import { PortalErrorPage } from './PortalErrorPage';

/**
 * Terminal confirmation shown after the vendor declines a revision request
 * from the SPA. The magic-link token is revoked at this point, so this
 * route is public (the JWT may already be dead) and has no further action.
 */
export function RevisionDeclinedPage() {
  return (
    <PortalErrorPage
      variant="info"
      title="Revision Declined"
      message="Thank you for your response. Your original bid remains in consideration. The project manager has been notified."
      helpText="No further action is needed. You may close this window."
      icon={
        <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8">
          <path
            d="M5 13l4 4L19 7"
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
