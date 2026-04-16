import { PortalErrorPage } from './PortalErrorPage';

export function BiddingClosedPage() {
  return (
    <PortalErrorPage
      variant="warning"
      title="Bidding is closed for this package"
      message="The BluOnX project manager has closed this bid package. No further submissions are being accepted."
      icon={
        <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8">
          <path
            d="M18.364 18.364A9 9 0 115.636 5.636m12.728 12.728L5.636 5.636"
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
