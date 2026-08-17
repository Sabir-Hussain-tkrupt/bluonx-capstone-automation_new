import { useState } from 'react';
import { Send } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/Toast/useToast';
import { errorMessage } from '@/lib/api';
import { useSendContract } from '@/features/contracts/hooks/useSendContract';

interface ContractNotSentAlertProps {
  awardId: string;
  /** Vendor company name, for the body copy. Falls back to "the vendor". */
  vendorCompanyName: string | null;
  /** Fires after a successful send, e.g. to clear a page-local failure state. */
  onSent?: () => void;
  className?: string;
}

/**
 * The award was recorded but the contract never reached the vendor.
 *
 * Rendered in exactly one situation: an active award at `pending_acceptance` with
 * no `docusign_envelopes` row. That is the only state where the post-commit send
 * is known to have failed and the send is still the right thing to do. Callers
 * must HIDE this rather than disable it everywhere else — a greyed-out button on
 * the happy path is clutter that invites clicking.
 *
 * Two surfaces use it: the task detail page (durable) and the comparison page
 * (moment-of-failure catch). One component, so the copy and the guardrails cannot
 * drift apart.
 *
 * "Send contract", never "Resend": nothing was ever sent. DocuSign's own resend
 * (for an envelope the vendor received but ignored) is a different feature.
 */
export function ContractNotSentAlert({
  awardId,
  vendorCompanyName,
  onSent,
  className,
}: ContractNotSentAlertProps) {
  const { toast } = useToast();
  const sendContract = useSendContract();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);

  const vendorLabel = vendorCompanyName || 'the vendor';

  function handleConfirm() {
    setSendError(null);
    sendContract.mutate(awardId, {
      onSuccess: () => {
        setConfirmOpen(false);
        toast({
          variant: 'success',
          title: 'Contract sent',
          message: `The contract is on its way to ${vendorLabel}.`,
        });
        onSent?.();
      },
      onError: (error) => {
        setConfirmOpen(false);
        // Into the Alert, not a toast: the PM needs to be able to read this,
        // come back to it, and quote it in a bug report.
        setSendError(errorMessage(error, 'Could not send the contract.'));
      },
    });
  }

  return (
    <>
      <Alert variant="warning" title="Contract not sent" className={className}>
        <p>
          The award was recorded but the contract was not delivered to{' '}
          <strong>{vendorLabel}</strong>. The vendor has not received anything.
        </p>

        {sendError && (
          <p className="mt-2 font-medium text-danger-700">{sendError}</p>
        )}

        <div className="mt-3">
          <Button
            size="sm"
            leftIcon={<Send className="h-4 w-4" />}
            // Button disables itself while isLoading. A double-click here is two
            // envelopes, so this is load-bearing, not decoration.
            isLoading={sendContract.isPending}
            onClick={() => {
              setSendError(null);
              setConfirmOpen(true);
            }}
          >
            Send contract
          </Button>
        </div>
      </Alert>

      <ConfirmDialog
        isOpen={confirmOpen}
        title="Send contract?"
        message={
          <>
            This sends the contract to <strong>{vendorLabel}</strong> for signature
            and emails their invited contact. Only do this if they have not received
            it already.
          </>
        }
        confirmText="Send contract"
        confirmVariant="primary"
        isLoading={sendContract.isPending}
        onConfirm={handleConfirm}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
