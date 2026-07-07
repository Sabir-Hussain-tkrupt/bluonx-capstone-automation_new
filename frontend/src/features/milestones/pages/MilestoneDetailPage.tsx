import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { TextInput } from '@/components/ui/TextInput';
import { FormField } from '@/components/ui/FormField';
import { useToast } from '@/components/ui/Toast/useToast';
import { useMilestone } from '@/features/milestones/hooks/useMilestone';
import { useUpdateMilestone } from '@/features/milestones/hooks/useUpdateMilestone';
import { useDeleteMilestone } from '@/features/milestones/hooks/useDeleteMilestone';
import { useMarkMilestoneStarted } from '@/features/milestones/hooks/useMarkMilestoneStarted';
import { useMarkMilestoneCompleted } from '@/features/milestones/hooks/useMarkMilestoneCompleted';
import { useRescheduleMilestone } from '@/features/milestones/hooks/useRescheduleMilestone';
import { MilestoneFormModal, type MilestoneFormValues } from '../components/MilestoneFormModal';
import { formatMilestoneDate } from '../utils/formatDate';

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
  const deleteMutation = useDeleteMilestone();
  const startMutation = useMarkMilestoneStarted();
  const completeMutation = useMarkMilestoneCompleted();
  const rescheduleMutation = useRescheduleMilestone();

  const [showEdit, setShowEdit] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [showReschedule, setShowReschedule] = useState(false);
  const [rescheduleEnd, setRescheduleEnd] = useState('');

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

  const handleDelete = () => {
    deleteMutation.mutate(milestone.id, {
      onSuccess: () => {
        toast({ variant: 'success', message: 'Milestone deleted.' });
        backToTask();
      },
      onError: onError('Failed to delete milestone.'),
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

  const handleComplete = () => {
    completeMutation.mutate(
      { id: milestone.id },
      {
        onSuccess: () => toast({ variant: 'success', message: 'Milestone marked completed.' }),
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
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z"
                clipRule="evenodd"
              />
            </svg>
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold text-secondary-900 sm:text-2xl">
              {milestone.name}
            </h1>
            <div className="mt-1">
              <StatusBadge status={milestone.status} />
            </div>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" onClick={() => setShowEdit(true)}>
            Edit
          </Button>
          <Button variant="danger" onClick={() => setShowDelete(true)}>
            Delete
          </Button>
        </div>
      </div>

      {/* Timeline + Notes */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <Card>
          <div className="p-6">
            <h3 className="mb-3 text-sm font-semibold text-secondary-900">Timeline</h3>
            <dl className="divide-y divide-secondary-100">
              <InfoRow label="Planned Start" value={formatMilestoneDate(milestone.start_date)} />
              <InfoRow label="Planned End" value={formatMilestoneDate(milestone.end_date)} />
              <InfoRow label="Actual Start" value={formatMilestoneDate(milestone.actual_start_date)} />
              <InfoRow label="Actual End" value={formatMilestoneDate(milestone.actual_end_date)} />
            </dl>
          </div>
        </Card>

        <Card>
          <div className="p-6">
            <h3 className="mb-3 text-sm font-semibold text-secondary-900">Notes</h3>
            {milestone.notes ? (
              <p className="whitespace-pre-wrap text-sm text-secondary-700">{milestone.notes}</p>
            ) : (
              <p className="text-sm text-secondary-500">No notes.</p>
            )}
          </div>
        </Card>
      </div>

      {/* Actions */}
      {(canStart || canComplete || canReschedule) && (
        <Card>
          <div className="flex flex-wrap items-center gap-2 p-6">
            {canStart && (
              <Button onClick={handleStart} isLoading={startMutation.isPending}>
                Mark Started
              </Button>
            )}
            {canComplete && (
              <Button
                variant="success"
                onClick={handleComplete}
                isLoading={completeMutation.isPending}
              >
                Mark Completed
              </Button>
            )}
            {canReschedule && (
              <Button variant="outline" onClick={() => setShowReschedule(true)}>
                Reschedule
              </Button>
            )}
          </div>
        </Card>
      )}

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
            value={rescheduleEnd}
            onChange={(e) => setRescheduleEnd(e.target.value)}
          />
        </FormField>
        <p className="mt-2 text-xs text-secondary-500">
          Rescheduling returns the milestone to In Progress.
        </p>
      </Modal>

      {/* Delete confirmation */}
      <Modal
        isOpen={showDelete}
        onClose={() => setShowDelete(false)}
        title="Delete Milestone"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowDelete(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={handleDelete} isLoading={deleteMutation.isPending}>
              Delete Milestone
            </Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          Are you sure you want to delete <strong>{milestone.name}</strong>? This cannot be undone.
        </p>
      </Modal>
    </div>
  );
}
