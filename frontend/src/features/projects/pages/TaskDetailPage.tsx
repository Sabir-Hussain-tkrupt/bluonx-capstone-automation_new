import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast/useToast';
import { useTask } from '@/features/tasks/hooks/useTask';
import { useProject } from '@/features/projects/hooks/useProject';
import { useUpdateTask } from '@/features/tasks/hooks/useUpdateTask';
import { useDeleteTask } from '@/features/tasks/hooks/useDeleteTask';
import { TaskForm } from '@/features/tasks/components/TaskForm';
import { useBidPackagesForTask } from '@/features/bids/hooks/useBidPackagesForTask';
import { BidPackagesTable } from '@/features/bids/components/BidPackagesTable';

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="shrink-0 text-secondary-500">{label}</dt>
      <dd className="text-right text-secondary-900">{value || '\u2014'}</dd>
    </div>
  );
}

function formatCurrency(value: number | null): string {
  if (value == null) return '\u2014';
  return Number(value).toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function formatPhase(phase: string): string {
  return phase === 'due_diligence' ? 'Due Diligence' : 'Development';
}

function formatBidType(bidType: string): string {
  switch (bidType) {
    case 'competitive': return 'Competitive';
    case 'direct_assign': return 'Direct Assign';
    case 'internal': return 'Internal';
    default: return bidType;
  }
}

function formatDate(value: string | null): string {
  if (!value) return '\u2014';
  return new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function TaskDetailPage() {
  const { id: projectId, taskId } = useParams<{ id: string; taskId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: task, isLoading, error } = useTask(projectId!, taskId!);
  const { data: project } = useProject(projectId!);
  const updateMutation = useUpdateTask();
  const deleteMutation = useDeleteTask(projectId!);

  const isArchived = !!project?.archived_at;

  const { data: bidPackages = [], isLoading: bidPackagesLoading } = useBidPackagesForTask(taskId!);

  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton height="32px" width="70%" />
        <Skeleton height="300px" />
      </div>
    );
  }

  if (error || !task) {
    return (
      <Alert variant="danger" title="Task not found">
        The task you are looking for does not exist or has been deleted.
      </Alert>
    );
  }

  const handleUpdate = (formData: Record<string, unknown>) => {
    updateMutation.mutate(
      { projectId: projectId!, taskId: taskId!, ...formData } as Parameters<typeof updateMutation.mutate>[0],
      {
        onSuccess: () => {
          setShowEditForm(false);
          toast({ variant: 'success', message: 'Task updated.' });
        },
        onError: (err) => {
          toast({ variant: 'danger', message: (err as { message?: string })?.message || 'Failed to update task.' });
        },
      },
    );
  };

  const handleDelete = () => {
    deleteMutation.mutate(taskId!, {
      onSuccess: () => {
        toast({ variant: 'success', message: 'Task deleted.' });
        navigate(`/projects/${projectId}`);
      },
      onError: (err) => {
        toast({ variant: 'danger', message: (err as { message?: string })?.message || 'Failed to delete task.' });
      },
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => navigate(`/projects/${projectId}`)}
            className="shrink-0 rounded-lg p-1 text-secondary-400 hover:bg-secondary-100 hover:text-secondary-600"
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
            <h1 className="truncate text-xl font-semibold text-secondary-900 sm:text-2xl">{task.name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <StatusBadge status={task.status} />
              <span className="text-xs text-secondary-400">{formatPhase(task.phase)}</span>
            </div>
          </div>
        </div>
        {!isArchived && (
          <div className="flex shrink-0 gap-2">
            <Button variant="outline" onClick={() => setShowEditForm(true)}>Edit</Button>
            <Button variant="danger" onClick={() => setShowDeleteConfirm(true)}>Delete</Button>
          </div>
        )}
      </div>

      {isArchived && (
        <Alert variant="info" title="Parent project is archived">
          Unarchive the project to make changes to this task.
        </Alert>
      )}

      {/* Task Details */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <Card>
          <div className="p-6">
            <h3 className="mb-3 text-sm font-semibold text-secondary-900">Task Details</h3>
            <dl className="divide-y divide-secondary-100">
              <InfoRow label="Trade" value={task.trade_name} />
              <InfoRow label="Phase" value={formatPhase(task.phase)} />
              <InfoRow label="Bid Type" value={formatBidType(task.bid_type)} />
              <InfoRow label="Status" value={<StatusBadge status={task.status} size="sm" />} />
              <InfoRow label="Budget Estimate" value={formatCurrency(task.budget_estimate)} />
              <InfoRow label="Sort Order" value={task.sort_order} />
            </dl>
          </div>
        </Card>

        <Card>
          <div className="p-6">
            <h3 className="mb-3 text-sm font-semibold text-secondary-900">Timestamps</h3>
            <dl className="divide-y divide-secondary-100">
              <InfoRow label="Created" value={formatDate(task.created_at)} />
              <InfoRow label="Updated" value={formatDate(task.updated_at)} />
            </dl>

            {task.description && (
              <div className="mt-6">
                <h3 className="mb-2 text-sm font-semibold text-secondary-900">Description</h3>
                <p className="text-sm text-secondary-700 whitespace-pre-wrap">{task.description}</p>
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Bid Packages Section */}
      {task.bid_type === 'competitive' && (
        <Card>
          <div className="p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-secondary-900">Bid Packages</h3>
              {task.status === 'draft' && !isArchived && (
                <Button
                  size="sm"
                  onClick={() => navigate(`/projects/${projectId}/tasks/${taskId}/create-bid-package`)}
                >
                  {bidPackages.length > 0 ? 'Start New Round' : 'Start Bidding'}
                </Button>
              )}
            </div>
            <BidPackagesTable
              bidPackages={bidPackages}
              isLoading={bidPackagesLoading}
              onRowClick={(row) =>
                navigate(`/projects/${projectId}/tasks/${taskId}/bid-packages/${row.id}`)
              }
            />
          </div>
        </Card>
      )}

      {/* Edit Task Modal */}
      <TaskForm
        isOpen={showEditForm}
        onClose={() => setShowEditForm(false)}
        task={task}
        onSubmit={handleUpdate}
        isLoading={updateMutation.isPending}
      />

      {/* Delete Confirmation */}
      <Modal
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        title="Delete Task"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowDeleteConfirm(false)}>Cancel</Button>
            <Button variant="danger" onClick={handleDelete} isLoading={deleteMutation.isPending}>Delete Task</Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          Are you sure you want to delete <strong>{task.name}</strong>?
          This action will soft-delete the task and it will no longer appear in lists.
        </p>
      </Modal>
    </div>
  );
}
