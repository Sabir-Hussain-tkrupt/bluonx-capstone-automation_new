import { Modal } from '../Modal';
import { Button } from '../Button';
import type { ComponentVariant } from '../types';

export interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  /** Body copy. Say what will happen, and whether it can be undone. */
  message: React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  /** Visual weight of the confirm button. Use 'danger' for destructive actions. */
  confirmVariant?: ComponentVariant;
  isLoading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Confirmation prompt for destructive actions.
 *
 * Built on Modal, which already handles Escape, focus save/restore and
 * portalling. Overlay-click dismissal is deliberately off: a stray click
 * should never be the thing standing between a user and a deleted record.
 */
export function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  confirmVariant = 'danger',
  isLoading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onCancel}
      title={title}
      size="sm"
      closeOnOverlayClick={false}
      mobileCenter
      footer={
        <>
          <Button variant="ghost" onClick={onCancel} disabled={isLoading}>
            {cancelText}
          </Button>
          <Button variant={confirmVariant} onClick={onConfirm} isLoading={isLoading}>
            {confirmText}
          </Button>
        </>
      }
    >
      <div className="text-sm text-secondary-600">{message}</div>
    </Modal>
  );
}
