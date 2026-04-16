import { PortalErrorPage } from './PortalErrorPage';

export function AlreadySubmittedPage() {
  return (
    <PortalErrorPage
      variant="info"
      title="A bid has already been submitted"
      message="Our records show that a bid for this invitation has already been received. Each vendor can only submit one bid per invitation."
      helpText={
        <>
          If you need to update your submission, please contact the BluOnX project manager
          directly.
        </>
      }
      icon={
        <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8">
          <path
            d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
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
