import { CheckCircle2 } from 'lucide-react';
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
      icon={<CheckCircle2 className="h-8 w-8" aria-hidden="true" />}
    />
  );
}
