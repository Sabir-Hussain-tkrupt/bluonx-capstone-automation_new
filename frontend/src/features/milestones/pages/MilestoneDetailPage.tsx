import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  CalendarClock,
  CheckCircle2,
  MoreHorizontal,
  Pencil,
  PlayCircle,
  XCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { IconButton } from '@/components/ui/IconButton';
import { Card } from '@/components/ui/Card';
import { DropdownMenu, DropdownMenuItem } from '@/components/ui/DropdownMenu';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { TextInput } from '@/components/ui/TextInput';
import { FormField } from '@/components/ui/FormField';
import { useToast } from '@/components/ui/Toast/useToast';
import { useMilestone } from '@/features/milestones/hooks/useMilestone';
import { useUpdateMilestone } from '@/features/milestones/hooks/useUpdateMilestone';
import { useMarkMilestoneStarted } from '@/features/milestones/hooks/useMarkMilestoneStarted';
import { useMarkMilestoneCompleted } from '@/features/milestones/hooks/useMarkMilestoneCompleted';
import { useRescheduleMilestone } from '@/features/milestones/hooks/useRescheduleMilestone';
import { useCancelMilestone } from '@/features/milestones/hooks/useCancelMilestone';
import { MilestoneFormModal, type MilestoneFormValues } from '../components/MilestoneFormModal';
import { MilestoneActivityTimeline } from '../components/MilestoneActivityTimeline';
import { MilestoneStatusBadge } from '../components/MilestoneStatusBadge';
import { formatMilestoneDate } from '../utils/formatDate';
import { todayStr } from '../utils/today';

const TERMINAL_STATUSES = new Set(['completed', 'cancelled']);
const RESCHEDULABLE_STATUSES = new Set(['in_progress', 'delayed', 'unresponsive']);

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="shrink-0 text-secondary-500">{label}</dt>
      <dd className="text-right text-secondary-900">{value ?? '—'}</dd>
    </div>
  );
}

export function MilestoneDetailPage() {
  const { id: projectId, taskId, milestoneId } = useParams<{
    id: string;
    taskId: string;
    milestoneId: string;
  }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: milestone, isLoading, error } = useMilestone(milestoneId!);
  const updateMutation = useUpdateMilestone();
  const startMutation = useMarkMilestoneStarted();
  const completeMutation = useMarkMilestoneCompleted();
  const rescheduleMutation = useRescheduleMilestone();
  const cancelMutation = useCancelMilestone();

  const [showEdit, setShowEdit] = useState(false);
  const [showReschedule, setShowReschedule] = useState(false);
  const [showComplete, setShowComplete] = useState(false);
  const [showCancel, setShowCancel] = useState(false);
  const [rescheduleEnd, setRescheduleEnd] = useState('');
  const [completeEnd, setCompleteEnd] = useState('');

  const backToTask = () => navigate(`/projects/${projectId}/tasks/${taskId}`);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton height="32px" width="60%" />
        <Skeleton height="240px" />
      </div>
    );
  }

  if (error || !milestone) {
    return (
      <Alert variant="danger" title="Milestone not found">
        The milestone you are looking for does not exist or has been deleted.
      </Alert>
    );
  }

  const onError = (fallback: string) => (err: unknown) =>
    toast({ variant: 'danger', message: (err as { message?: string })?.message || fallback });

  const handleEdit = (data: MilestoneFormValues) => {
    updateMutation.mutate(
      {
        id: milestone.id,
        name: data.name,
        start_date: data.start_date,
        end_date: data.end_date,
        notes: data.notes ?? null,
      },
      {
        onSuccess: () => {
          setShowEdit(false);
          toast({ variant: 'success', message: 'Milestone updated.' });
        },
        onError: onError('Failed to update milestone.'),
      },
    );
  };

  const handleCancel = () => {
    cancelMutation.mutate(milestone.id, {
      onSuccess: () => {
        setShowCancel(false);
        toast({ variant: 'success', message: 'Milestone cancelled.' });
      },
      onError: onError('Failed to cancel milestone.'),
    });
  };

  const handleStart = () => {
    startMutation.mutate(
      { id: milestone.id },
      {
        onSuccess: () => toast({ variant: 'success', message: 'Milestone marked started.' }),
        onError: onError('Failed to mark started.'),
      },
    );
  };

  const openComplete = () => {
    // Prefill today, but the PM can back-date when catching the system up after
    // the fact. The backend rejects (422) an end that predates the actual start.
    setCompleteEnd(milestone.actual_end_date ?? todayStr());
    setShowComplete(true);
  };

  const handleComplete = () => {
    completeMutation.mutate(
      { id: milestone.id, actualEndDate: completeEnd },
      {
        onSuccess: () => {
          setShowComplete(false);
          toast({ variant: 'success', message: 'Milestone marked completed.' });
        },
        onError: onError('Failed to mark completed.'),
      },
    );
  };

  const handleReschedule = () => {
    rescheduleMutation.mutate(
      { id: milestone.id, endDate: rescheduleEnd },
      {
        onSuccess: () => {
          setShowReschedule(false);
          setRescheduleEnd('');
          toast({ variant: 'success', message: 'Milestone rescheduled.' });
        },
        onError: onError('Failed to reschedule milestone.'),
      },
    );
  };

  const canStart = milestone.status === 'scheduled';
  const canComplete = !TERMINAL_STATUSES.has(milestone.status);
  const canReschedule = RESCHEDULABLE_STATUSES.has(milestone.status);
  const canCancel = !TERMINAL_STATUSES.has(milestone.status);
  const datesLocked = milestone.status !== 'scheduled';
  const endDrifted =
    !!milestone.baseline_end_date && milestone.end_date !== milestone.baseline_end_date;
  const responses = milestone.milestone_responses ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={backToTask}
            className="shrink-0 rounded-lg p-1 text-secondary-400 hover:bg-secondary-100 hover:text-secondary-600"
            aria-label="Back to task"
          >
            <ArrowLeft className="h-5 w-5" aria-hidden="true" />
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold text-secondary-900 sm:text-2xl">
              {milestone.name}
            </h1>
            <div className="mt-1">
              <MilestoneStatusBadge status={milestone.status} />
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {canStart && (
            <Button
              variant="success"
              leftIcon={<PlayCircle className="h-4 w-4" />}
              onClick={handleStart}
              isLoading={startMutation.isPending}
            >
              Mark Started
            </Button>
          )}
          {canComplete && (
            <Button
              variant="success"
              leftIcon={<CheckCircle2 className="h-4 w-4" />}
              onClick={openComplete}
            >
              Mark Completed
            </Button>
          )}
          {canReschedule && (
            <Button
              variant="outline"
              leftIcon={<CalendarClock className="h-4 w-4" />}
              onClick={() => setShowReschedule(true)}
            >
              Reschedule
            </Button>
          )}
          <Button
            variant="primary"
            leftIcon={<Pencil className="h-4 w-4" />}
            onClick={() => setShowEdit(true)}
          >
            Edit
          </Button>
          {canCancel && (
            <DropdownMenu
              trigger={
                <IconButton
                  variant="outline"
                  size="md"
                  icon={<MoreHorizontal className="h-4 w-4" />}
                  aria-label="More actions"
                />
              }
            >
              <DropdownMenuItem
                icon={<XCircle className="h-4 w-4" />}
                destructive
                onClick={() => setShowCancel(true)}
              >
                Cancel Milestone
              </DropdownMenuItem>
            </DropdownMenu>
          )}
        </div>
      </div>

      {/* Timeline + Notes */}
      <Card>
        <div className="p-6">
          <div className="space-y-6">
            <section>
              <h3 className="mb-3 border-b border-secondary-100 pb-2 text-base font-semibold text-secondary-900">
                Timeline
              </h3>
              <dl className="divide-y divide-secondary-100">
                <InfoRow label="Planned Start" value={formatMilestoneDate(milestone.start_date)} />
                <InfoRow
                  label="Planned End"
                  value={
                    endDrifted ? (
                      <span>
                        {formatMilestoneDate(milestone.end_date)}{' '}
                        <span className="text-warning-600">
                          (committed: {formatMilestoneDate(milestone.baseline_end_date)})
                        </span>
                      </span>
                    ) : (
                      formatMilestoneDate(milestone.end_date)
                    )
                  }
                />
                <InfoRow
                  label="Actual Start"
                  value={formatMilestoneDate(milestone.actual_start_date)}
                />
                <InfoRow label="Actual End" value={formatMilestoneDate(milestone.actual_end_date)} />
              </dl>
            </section>

            <section>
              <h3 className="mb-3 border-b border-secondary-100 pb-2 text-base font-semibold text-secondary-900">
                Notes
              </h3>
              {milestone.notes ? (
                <p className="text-sm leading-relaxed whitespace-pre-wrap text-secondary-700">
                  {milestone.notes}
                </p>
              ) : (
                <p className="text-sm text-secondary-500 italic">No notes.</p>
              )}
            </section>
          </div>
        </div>
      </Card>

      {/* Activity timeline (the unified ledger narrative) */}
      <MilestoneActivityTimeline milestoneId={milestone.id} />

      {/* Response History */}
      <Card>
        <div className="p-6">
          <h3 className="mb-3 text-sm font-semibold text-secondary-900">Response History</h3>
          {responses.length === 0 ? (
            <p className="text-sm text-secondary-500">No responses recorded yet.</p>
          ) : (
            <ul className="divide-y divide-secondary-100">
              {responses.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-4 py-2 text-sm">
                  <div>
                    <span className="font-medium text-secondary-900">
                      {r.vendor_contacts?.full_name ?? 'Vendor'}
                    </span>
                    <span className="ml-2 text-secondary-500">{r.response_type}</span>
                  </div>
                  <div className="text-right text-secondary-500">
                    <span className="mr-2 font-medium text-secondary-700">{r.response_value}</span>
                    {formatMilestoneDate(r.responded_at.slice(0, 10))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      {/* Edit modal */}
      <MilestoneFormModal
        isOpen={showEdit}
        onClose={() => setShowEdit(false)}
        milestone={milestone}
        onSubmit={handleEdit}
        isLoading={updateMutation.isPending}
        datesLocked={datesLocked}
      />

      {/* Reschedule modal */}
      <Modal
        isOpen={showReschedule}
        onClose={() => setShowReschedule(false)}
        title="Reschedule Milestone"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowReschedule(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleReschedule}
              isLoading={rescheduleMutation.isPending}
              disabled={!rescheduleEnd}
            >
              Reschedule
            </Button>
          </>
        }
      >
        <FormField label="New End Date" required>
          <TextInput
            type="date"
            min={todayStr()}
            value={rescheduleEnd}
            onChange={(e) => setRescheduleEnd(e.target.value)}
          />
        </FormField>
        <p className="mt-2 text-xs text-secondary-500">
          Rescheduling returns the milestone to In Progress.
        </p>
      </Modal>

      {/* Mark Completed modal */}
      <Modal
        isOpen={showComplete}
        onClose={() => setShowComplete(false)}
        title="Mark Completed"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowComplete(false)}>
              Cancel
            </Button>
            <Button
              variant="success"
              onClick={handleComplete}
              isLoading={completeMutation.isPending}
              disabled={!completeEnd}
            >
              Mark Completed
            </Button>
          </>
        }
      >
        <FormField label="Actual End Date" required>
          <TextInput
            type="date"
            value={completeEnd}
            min={milestone.actual_start_date ?? undefined}
            onChange={(e) => setCompleteEnd(e.target.value)}
          />
        </FormField>
        <p className="mt-2 text-xs text-secondary-500">
          Defaults to today. Set the date the work actually finished if you are recording it later.
        </p>
      </Modal>

      {/* Cancel confirmation */}
      <Modal
        isOpen={showCancel}
        onClose={() => setShowCancel(false)}
        title="Cancel Milestone"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowCancel(false)}>
              Keep Milestone
            </Button>
            <Button variant="danger" onClick={handleCancel} isLoading={cancelMutation.isPending}>
              Cancel Milestone
            </Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          Cancel <strong>{milestone.name}</strong>? It stays on record (with its full activity
          history) but is retired from the schedule. This is how a milestone is removed —
          whether it was created by mistake or is no longer going ahead.
        </p>
      </Modal>
    </div>
  );
}
