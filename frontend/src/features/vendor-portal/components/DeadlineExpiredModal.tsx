import { Button, Modal } from '@/components/ui';

export interface DeadlineExpiredModalProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Shown when a write request (save, submit, upload, delete) is rejected
 * because the bid package deadline passed mid-session. The draft is
 * safely persisted up to the last successful save — we just can't
 * mutate it anymore. Closing the modal leaves the form in read-only
 * mode; BidFormPage locks Submit and uploads once the flag is set.
 */
export function DeadlineExpiredModal({ open, onClose }: DeadlineExpiredModalProps) {
  return (
    <Modal
      isOpen={open}
      onClose={onClose}
      title="Bid Deadline Passed"
      size="sm"
      mobileCenter
      closeOnOverlayClick={false}
      footer={
        <Button variant="primary" onClick={onClose}>
          Understood
        </Button>
      }
    >
      <p className="text-sm text-secondary-700">
        The bid deadline has passed. Your draft has been saved but cannot be
        submitted. Please reach out to the project team if you believe this is
        an error.
      </p>
    </Modal>
  );
}
