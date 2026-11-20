import { useState } from 'react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Checkbox } from '@/components/ui/Checkbox';
import { FormField } from '@/components/ui/FormField';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { formatMoney } from '@/features/budgets/utils/money';
import { useBiddingCheckpoint, useCompleteBidding } from '../hooks/useContingency';
import type { CheckpointOutcome } from '../types';
import { formatPercent, textareaClass } from './shared';

interface BiddingCompleteModalProps {
  projectId: string;
  isOpen: boolean;
  onClose: () => void;
}

const BID_TYPE_LABEL: Record<string, string> = {
  competitive: 'Competitive',
  direct_assign: 'Direct assign',
};

/**
 * Task 3.4 — the bidding-complete checkpoint. Lists every competitive or
 * direct-assign task still without an award, shows the contingency that will
 * be left, and says whether it will escalate to the executives.
 */
export function BiddingCompleteModal({ projectId, isOpen, onClose }: BiddingCompleteModalProps) {
  const { toast } = useToast();
  const preview = useBiddingCheckpoint(projectId, isOpen);
  const complete = useCompleteBidding(projectId);
  // Mounted only while open, so every opening starts unticked and empty.
  const [acknowledged, setAcknowledged] = useState(false);
  const [note, setNote] = useState('');

  const data = preview.data;
  const openTasks = data?.open_tasks ?? [];
  const blocked = openTasks.length > 0 && !acknowledged;

  const submit = () => {
    complete.mutate(
      { note: note.trim() || null, acknowledge_open_tasks: acknowledged },
      {
        onSuccess: (res) => {
          const messages: Record<CheckpointOutcome, string> = {
            on_target: 'Bidding marked complete. Contingency is on target; nothing is released.',
            below_target: 'Bidding marked complete. Contingency is below target.',
            escalated: 'Bidding marked complete. Contingency is far below target: the executives and finance have been notified.',
            no_base: 'Bidding marked complete.',
          };
          toast({ variant: res.outcome === 'escalated' ? 'warning' : 'success', message: messages[res.outcome] });
          onClose();
        },
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not mark bidding complete.') }),
      },
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={() => !complete.isPending && onClose()}
      title="Mark bidding complete"
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={complete.isPending}>Cancel</Button>
          <Button onClick={submit} isLoading={complete.isPending} disabled={!data || blocked}>
            Mark bidding complete
          </Button>
        </>
      }
    >
      {preview.isLoading ? (
        <div className="space-y-3">
          <Skeleton height="72px" />
          <Skeleton height="120px" />
        </div>
      ) : preview.isError || !data ? (
        <Alert variant="danger" title="Could not load the checkpoint">
          {errorMessage(preview.error, 'Something went wrong. Please try again.')}
        </Alert>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-3 rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-3 text-sm sm:grid-cols-3">
            <div>
              <div className="text-secondary-500">Contingency left</div>
              <div className="font-semibold tabular-nums text-secondary-900">{formatMoney(data.contingency)}</div>
            </div>
            <div>
              <div className="text-secondary-500">Of the contingency base</div>
              <div className="font-semibold tabular-nums text-secondary-900">
                {formatPercent(data.left_percent)} of {formatMoney(data.base)}
              </div>
            </div>
            <div>
              <div className="text-secondary-500">Target</div>
              <div className="font-semibold tabular-nums text-secondary-900">
                {formatPercent(data.target_percent)} (escalates at {formatPercent(data.escalation_percent)})
              </div>
            </div>
          </div>

          {data.predicted_outcome === 'escalated' && (
            <Alert variant="danger" title="This will escalate to the executives">
              Contingency is far below the {formatPercent(data.target_percent)} target. The executives and the head of
              finance are emailed so they can act before sale prices are set.
            </Alert>
          )}
          {data.predicted_outcome === 'below_target' && (
            <Alert variant="warning" title="Contingency is below target">
              It is above the escalation level, so no one is escalated, but the shortfall is recorded.
            </Alert>
          )}
          {data.predicted_outcome === 'on_target' && (
            <Alert variant="success" title="Contingency is on target">
              Contingency stays as it is. Nothing is released early.
            </Alert>
          )}

          {openTasks.length > 0 ? (
            <div className="space-y-2">
              <Alert variant="warning" title={`${openTasks.length} task${openTasks.length === 1 ? '' : 's'} without an award`}>
                These competitive or direct-assign tasks have no award yet. Their budget lines still hold the estimate.
              </Alert>
              <ul className="max-h-48 divide-y divide-secondary-100 overflow-y-auto rounded-lg border border-secondary-200 text-sm">
                {openTasks.map((t) => (
                  <li key={t.id} className="flex items-center justify-between px-3 py-2">
                    <span className="font-medium text-secondary-900">{t.name}</span>
                    <span className="text-xs text-secondary-500">{BID_TYPE_LABEL[t.bid_type] ?? t.bid_type}</span>
                  </li>
                ))}
              </ul>
              <Checkbox
                label="I have reviewed these tasks and want to mark bidding complete anyway"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
              />
            </div>
          ) : (
            <p className="text-sm text-secondary-600">Every competitive and direct-assign task has an award.</p>
          )}

          <FormField label="Note" htmlFor="bidding-note" hint="Optional. Saved with the checkpoint.">
            <textarea
              id="bidding-note"
              rows={3}
              maxLength={2000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className={textareaClass}
            />
          </FormField>
        </div>
      )}
    </Modal>
  );
}
