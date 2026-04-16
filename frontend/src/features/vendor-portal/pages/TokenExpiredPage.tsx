import { PortalErrorPage } from './PortalErrorPage';

export function TokenExpiredPage() {
  return (
    <PortalErrorPage
      variant="warning"
      title="This bid link has expired"
      message="Magic links expire when the bid deadline passes. Please contact the BluOnX project manager if you still need to submit."
      icon={
        <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8">
          <path
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
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
