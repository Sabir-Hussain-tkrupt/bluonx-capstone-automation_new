import { AlertTriangle } from 'lucide-react';
import { PortalErrorPage } from './PortalErrorPage';

export function InvalidTokenPage() {
  return (
    <PortalErrorPage
      variant="danger"
      title="This bid link is not recognized"
      message="The magic link in your email might be incomplete or incorrect. Please re-open the email and click the Submit Bid button again."
      icon={<AlertTriangle className="h-8 w-8" aria-hidden="true" />}
    />
  );
}
