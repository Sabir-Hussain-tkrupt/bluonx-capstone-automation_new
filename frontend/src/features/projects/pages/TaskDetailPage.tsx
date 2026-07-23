import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { IconButton } from '@/components/ui/IconButton';
import { DropdownMenu, DropdownMenuItem } from '@/components/ui/DropdownMenu';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { Field } from '@/components/ui/Field';
import { useToast } from '@/components/ui/Toast/useToast';
import { formatCurrency } from '@/lib/format';
import { errorMessage, type ApiError } from '@/lib/api';
import { useTask } from '@/features/tasks/hooks/useTask';
import { useProject } from '@/features/projects/hooks/useProject';
import { useUpdateTask } from '@/features/tasks/hooks/useUpdateTask';
import { useDeleteTask } from '@/features/tasks/hooks/useDeleteTask';
import { TaskForm } from '@/features/tasks/components/TaskForm';
import { useBidPackagesForTask } from '@/features/bids/hooks/useBidPackagesForTask';
import { BidPackagesTable } from '@/features/bids/components/BidPackagesTable';
import { useTaskActiveContract } from '@/features/milestones/hooks/useTaskActiveContract';
import { MilestonesCard } from '@/features/milestones/components/MilestonesCard';
import { ContractPanel } from '@/features/contracts/components/ContractPanel';

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

  const { data: task, isLoading, error, refetch, isFetching } = useTask(projectId!, taskId!);
  const { data: project } = useProject(projectId!);
  const updateMutation = useUpdateTask();
  const deleteMutation = useDeleteTask(projectId!);

  const isArchived = !!project?.archived_at;

  const { data: bidPackages = [], isLoading: bidPackagesLoading } = useBidPackagesForTask(taskId!);
  const { data: activeContract } = useTaskActiveContract(taskId!);

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

  if (error) {
    const status = (error as unknown as ApiError | undefined)?.status;
    if (status !== 404) {
      return (
        <Alert variant="danger" title="Could not load task">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>{errorMessage(error, 'Something went wrong. Please try again.')}</span>
            <Button variant="outline" size="sm" onClick={() => refetch()} isLoading={isFetching}>
              Retry
            </Button>
          </div>
        </Alert>
      );
    }
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
          toast({ variant: 'danger', message: errorMessage(err, 'Failed to update task.') });
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
        toast({ variant: 'danger', message: errorMessage(err, 'Failed to delete task.') });
      },
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <IconButton
            variant="ghost"
            size="sm"
            icon={<ArrowLeft className="h-4 w-4" />}
            aria-label="Back"
            onClick={() => navigate(`/projects/${projectId}`)}
            className="shrink-0"
          />
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold text-secondary-900 sm:text-2xl">{task.name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <StatusBadge status={task.status} />
              <span className="text-xs text-secondary-400">{formatPhase(task.phase)}</span>
            </div>
          </div>
        </div>
        {!isArchived && (
          <div className="flex shrink-0 items-center gap-2">
            <Button
              variant="primary"
              leftIcon={<Pencil className="h-4 w-4" />}
              onClick={() => setShowEditForm(true)}
            >
              Edit
            </Button>
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
                icon={<Trash2 className="h-4 w-4" />}
                destructive
                onClick={() => setShowDeleteConfirm(true)}
              >
                Delete
              </DropdownMenuItem>
            </DropdownMenu>
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
            <h3 className="mb-4 border-b border-secondary-100 pb-2 text-base font-semibold text-secondary-900">Task Details</h3>
            <dl className="divide-y divide-secondary-100">
              <Field label="Trade" value={task.trade_name} />
              <Field label="Phase" value={formatPhase(task.phase)} />
              <Field label="Bid Type" value={formatBidType(task.bid_type)} />
              <Field label="Status" value={<StatusBadge status={task.status} size="sm" />} />
              <Field label="Budget Estimate" value={formatCurrency(task.budget_estimate)} />
              <Field label="Sort Order" value={task.sort_order} />
            </dl>
          </div>
        </Card>

        <Card>
          <div className="p-6">
            <h3 className="mb-4 border-b border-secondary-100 pb-2 text-base font-semibold text-secondary-900">Timestamps</h3>
            <dl className="divide-y divide-secondary-100">
              <Field label="Created" value={formatDate(task.created_at)} />
              <Field label="Updated" value={formatDate(task.updated_at)} />
            </dl>

            {task.description && (
              <div className="mt-6">
                <h3 className="mb-4 border-b border-secondary-100 pb-2 text-base font-semibold text-secondary-900">Description</h3>
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
              <h3 className="text-base font-semibold text-secondary-900">Bid Packages</h3>
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

      {/* Contract panel — mark-complete gate + vendor rating, once contracted */}
      {activeContract && <ContractPanel taskId={taskId!} contract={activeContract} />}

      {/* Milestones Section — only once the task has an active contract */}
      {activeContract && <MilestonesCard taskId={taskId!} projectId={projectId!} />}

      {/* Edit Task Modal */}
      <TaskForm
        isOpen={showEditForm}
        onClose={() => setShowEditForm(false)}
        task={task}
        onSubmit={handleUpdate}
        isLoading={updateMutation.isPending}
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        title="Delete Task"
        message={
          <>
            Are you sure you want to delete <strong>{task.name}</strong>? This soft-deletes
            the task and it will no longer appear in lists.
          </>
        }
        confirmText="Delete Task"
        isLoading={deleteMutation.isPending}
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </div>
  );
}
