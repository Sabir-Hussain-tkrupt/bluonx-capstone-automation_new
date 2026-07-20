import { Ban } from 'lucide-react';
import { PortalErrorPage } from './PortalErrorPage';

export function BiddingClosedPage() {
  return (
    <PortalErrorPage
      variant="warning"
      title="Bidding is closed for this package"
      message="The BluOnX project manager has closed this bid package. No further submissions are being accepted."
      icon={<Ban className="h-8 w-8" aria-hidden="true" />}
    />
  );
}
