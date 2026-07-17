import { useState } from 'react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast/useToast';
import { useMilestonesForTask } from '@/features/milestones/hooks/useMilestonesForTask';
import type { TaskActiveContract } from '@/features/milestones/api/milestone.queries';
import { useMarkContractComplete } from '@/features/contracts/hooks/useMarkContractComplete';
import { useContractReview } from '@/features/contracts/hooks/useContractReview';
import { ReviewPanel } from './ReviewPanel';

interface ContractPanelProps {
  taskId: string;
  contract: TaskActiveContract;
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  sent_for_signature: 'Sent for signature',
  executed: 'Executed',
  active: 'Active',
  completed: 'Completed',
  terminated: 'Terminated',
};

export function ContractPanel({ taskId, contract }: ContractPanelProps) {
  const { toast } = useToast();
  const { data: milestones = [], isLoading: milestonesLoading } = useMilestonesForTask(taskId);
  const markComplete = useMarkContractComplete();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const isCompleted = contract.status === 'completed';

  // Review is only relevant once completed; skip the read until then.
  const { data: review, isLoading: reviewLoading } = useContractReview(
    isCompleted ? contract.id : undefined,
  );

  // Gate: every milestone completed/cancelled (or none). The RPC re-checks under a
  // lock server-side; this only decides whether to SHOW the button. Wait for the
  // milestone list to load first — an empty array while loading would read as
  // "all done" (vacuous every()) and flash the button on an open contract.
  const allDone = milestones.every(
    (m) => m.status === 'completed' || m.status === 'cancelled',
  );
  const canComplete =
    !isCompleted && contract.status !== 'terminated' && !milestonesLoading && allDone;

  const handleConfirm = () => {
    markComplete.mutate(contract.id, {
      onSuccess: () => {
        setConfirmOpen(false);
        toast({ variant: 'success', message: 'Contract marked complete.' });
      },
      onError: (err) => {
        setConfirmOpen(false);
        toast({
          variant: 'danger',
          message: (err as { message?: string })?.message || 'Failed to complete contract.',
        });
      },
    });
  };

  return (
    <Card>
      <div className="p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-secondary-900">Contract</h3>
            <p className="mt-0.5 text-xs text-secondary-500">
              {contract.contract_number} · {STATUS_LABELS[contract.status] ?? contract.status}
            </p>
          </div>
          {canComplete && (
            <Button size="sm" onClick={() => setConfirmOpen(true)}>
              Mark contract complete
            </Button>
          )}
        </div>

        {!isCompleted && !canComplete && !milestonesLoading && contract.status !== 'terminated' && (
          <p className="text-sm text-secondary-500">
            Complete or cancel every milestone before marking this contract complete.
          </p>
        )}

        {isCompleted &&
          (reviewLoading ? (
            <Skeleton height="120px" />
          ) : (
            <ReviewPanel
              contractId={contract.id}
              existingReview={review ?? null}
              milestones={milestones}
            />
          ))}
      </div>

      <Modal
        isOpen={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Mark contract complete?"
        size="sm"
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setConfirmOpen(false)}
              disabled={markComplete.isPending}
            >
              Cancel
            </Button>
            <Button onClick={handleConfirm} isLoading={markComplete.isPending}>
              Mark complete
            </Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          This closes the contract for {contract.contract_number}. You can then rate the vendor&apos;s
          performance. This cannot be undone.
        </p>
      </Modal>
    </Card>
  );
}
