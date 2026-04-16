import { PortalErrorPage } from './PortalErrorPage';

export function InvalidTokenPage() {
  return (
    <PortalErrorPage
      variant="danger"
      title="This bid link is not recognized"
      message="The magic link in your email might be incomplete or incorrect. Please re-open the email and click the Submit Bid button again."
      icon={
        <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8">
          <path
            d="M12 9v3.75m0 3.75h.008M10.44 3.102a1.873 1.873 0 013.12 0l8.25 14.25a1.875 1.875 0 01-1.624 2.805H3.814a1.875 1.875 0 01-1.624-2.805l8.25-14.25z"
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
