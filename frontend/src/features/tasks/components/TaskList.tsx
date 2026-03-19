import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Modal } from '@/components/ui/Modal';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast/useToast';
import { useTasks } from '@/features/tasks/hooks/useTasks';
import { useCreateTask } from '@/features/tasks/hooks/useCreateTask';
import { useUpdateTask } from '@/features/tasks/hooks/useUpdateTask';
import { useDeleteTask } from '@/features/tasks/hooks/useDeleteTask';
import { TaskForm } from './TaskForm';
import type { Task } from '@/features/tasks/api/task.queries';

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

interface TaskListProps {
  projectId: string;
  projectBudget?: number | null;
}

export function TaskList({ projectId, projectBudget }: TaskListProps) {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editTask, setEditTask] = useState<Task | undefined>();
  const [deleteTarget, setDeleteTarget] = useState<Task | undefined>();

  const { data, isLoading, error } = useTasks({ projectId, page_size: 100 });
  const createMutation = useCreateTask(projectId);
  const updateMutation = useUpdateTask();
  const deleteMutation = useDeleteTask(projectId);

  const tasks = data?.items ?? [];

  // Budget summary
  const totalTaskBudget = useMemo(
    () => tasks.reduce((sum, t) => sum + (t.budget_estimate ?? 0), 0),
    [tasks],
  );
  const budgetRemaining = projectBudget != null ? projectBudget - totalTaskBudget : null;
  const isOverBudget = budgetRemaining != null && budgetRemaining < 0;

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton height="40px" />
        <Skeleton height="200px" />
      </div>
    );
  }

  if (error) {
    return <Alert variant="danger" title="Failed to load tasks">Could not fetch tasks for this project.</Alert>;
  }

  const handleCreate = (formData: Record<string, unknown>) => {
    createMutation.mutate(formData as Parameters<typeof createMutation.mutate>[0], {
      onSuccess: () => {
        setShowCreateForm(false);
        toast({ variant: 'success', message: 'Task created.' });
      },
      onError: (err) => {
        toast({ variant: 'danger', message: (err as { message?: string })?.message || 'Failed to create task.' });
      },
    });
  };

  const handleUpdate = (formData: Record<string, unknown>) => {
    if (!editTask) return;
    updateMutation.mutate(
      { projectId, taskId: editTask.id, ...formData } as Parameters<typeof updateMutation.mutate>[0],
      {
        onSuccess: () => {
          setEditTask(undefined);
          toast({ variant: 'success', message: 'Task updated.' });
        },
        onError: (err) => {
          toast({ variant: 'danger', message: (err as { message?: string })?.message || 'Failed to update task.' });
        },
      },
    );
  };

  const handleDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => {
        setDeleteTarget(undefined);
        toast({ variant: 'success', message: 'Task deleted.' });
      },
      onError: (err) => {
        toast({ variant: 'danger', message: (err as { message?: string })?.message || 'Failed to delete task. It may have active bids, awards, or contracts.' });
      },
    });
  };

  return (
    <div className="space-y-4">
      {/* Header with Add button and budget summary */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          {projectBudget != null && (
            <>
              <span className="text-secondary-500">
                Project Budget: <strong className="text-secondary-900">{formatCurrency(projectBudget)}</strong>
              </span>
              <span className="text-secondary-300">|</span>
              <span className="text-secondary-500">
                Allocated: <strong className="text-secondary-900">{formatCurrency(totalTaskBudget)}</strong>
              </span>
              <span className="text-secondary-300">|</span>
              <span className={isOverBudget ? 'text-danger-600 font-semibold' : 'text-secondary-500'}>
                Remaining: <strong>{formatCurrency(budgetRemaining!)}</strong>
              </span>
            </>
          )}
        </div>
        <Button onClick={() => setShowCreateForm(true)}>Add Task</Button>
      </div>

      {isOverBudget && (
        <Alert variant="warning" title="Over Budget">
          Task budget estimates exceed the project budget by {formatCurrency(Math.abs(budgetRemaining!))}.
        </Alert>
      )}

      {/* Task list */}
      {tasks.length === 0 ? (
        <EmptyState
          title="No tasks yet"
          description="Create your first task to start building the bid pipeline for this project."
        />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-secondary-200">
                  <th className="px-4 py-3 font-medium text-secondary-500">#</th>
                  <th className="px-4 py-3 font-medium text-secondary-500">Name</th>
                  <th className="px-4 py-3 font-medium text-secondary-500 hidden md:table-cell">Trade</th>
                  <th className="px-4 py-3 font-medium text-secondary-500 hidden lg:table-cell">Phase</th>
                  <th className="px-4 py-3 font-medium text-secondary-500 hidden lg:table-cell">Bid Type</th>
                  <th className="px-4 py-3 font-medium text-secondary-500">Status</th>
                  <th className="px-4 py-3 font-medium text-secondary-500 hidden sm:table-cell text-right">Budget</th>
                  <th className="px-4 py-3 font-medium text-secondary-500 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-secondary-100">
                {tasks.map((task, idx) => (
                  <tr
                    key={task.id}
                    className="hover:bg-secondary-50 cursor-pointer transition-colors"
                    onClick={() => navigate(`/projects/${projectId}/tasks/${task.id}`)}
                  >
                    <td className="px-4 py-3 text-secondary-400">{idx + 1}</td>
                    <td className="px-4 py-3 font-medium text-secondary-900">{task.name}</td>
                    <td className="px-4 py-3 text-secondary-600 hidden md:table-cell">{task.trade_name ?? '\u2014'}</td>
                    <td className="px-4 py-3 text-secondary-600 hidden lg:table-cell">{formatPhase(task.phase)}</td>
                    <td className="px-4 py-3 text-secondary-600 hidden lg:table-cell">{formatBidType(task.bid_type)}</td>
                    <td className="px-4 py-3"><StatusBadge status={task.status} size="sm" /></td>
                    <td className="px-4 py-3 text-secondary-600 hidden sm:table-cell text-right">{formatCurrency(task.budget_estimate)}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          className="rounded p-1 text-secondary-400 hover:bg-secondary-100 hover:text-secondary-600"
                          title="Edit task"
                          onClick={() => setEditTask(task)}
                        >
                          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                            <path d="M2.695 14.763l-1.262 3.154a.5.5 0 00.65.65l3.155-1.262a4 4 0 001.343-.885L17.5 5.5a2.121 2.121 0 00-3-3L3.58 13.42a4 4 0 00-.885 1.343z" />
                          </svg>
                        </button>
                        <button
                          type="button"
                          className="rounded p-1 text-secondary-400 hover:bg-danger-50 hover:text-danger-600"
                          title="Delete task"
                          onClick={() => setDeleteTarget(task)}
                        >
                          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z" clipRule="evenodd" />
                          </svg>
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Create Task Modal */}
      <TaskForm
        isOpen={showCreateForm}
        onClose={() => setShowCreateForm(false)}
        onSubmit={handleCreate}
        isLoading={createMutation.isPending}
      />

      {/* Edit Task Modal */}
      <TaskForm
        isOpen={!!editTask}
        onClose={() => setEditTask(undefined)}
        task={editTask}
        onSubmit={handleUpdate}
        isLoading={updateMutation.isPending}
      />

      {/* Delete Confirmation */}
      <Modal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(undefined)}
        title="Delete Task"
        size="sm"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleteTarget(undefined)}>Cancel</Button>
            <Button variant="danger" onClick={handleDelete} isLoading={deleteMutation.isPending}>Delete Task</Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          Are you sure you want to delete <strong>{deleteTarget?.name}</strong>?
          This action will soft-delete the task and it will no longer appear in lists.
        </p>
      </Modal>
    </div>
  );
}
