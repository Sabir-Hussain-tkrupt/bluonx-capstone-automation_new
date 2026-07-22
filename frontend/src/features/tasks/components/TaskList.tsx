import { useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  DndContext,
  DragOverlay,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  verticalListSortingStrategy,
  arrayMove,
  sortableKeyboardCoordinates,
} from '@dnd-kit/sortable';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast/useToast';
import { errorMessage } from '@/lib/api';
import { useTasks } from '@/features/tasks/hooks/useTasks';
import { useCreateTask } from '@/features/tasks/hooks/useCreateTask';
import { useUpdateTask } from '@/features/tasks/hooks/useUpdateTask';
import { useDeleteTask } from '@/features/tasks/hooks/useDeleteTask';
import { useReorderTasks } from '@/features/tasks/hooks/useReorderTasks';
import { TaskForm } from './TaskForm';
import { SortableTaskRow, TaskRowOverlay } from './SortableTaskRow';
import type { Task } from '@/features/tasks/api/task.queries';

function formatCurrency(value: number | null): string {
  if (value == null) return '\u2014';
  return Number(value).toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

interface TaskListProps {
  projectId: string;
  projectBudget?: number | null;
  readOnly?: boolean;
}

export function TaskList({ projectId, projectBudget, readOnly = false }: TaskListProps) {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editTask, setEditTask] = useState<Task | undefined>();
  const [deleteTarget, setDeleteTarget] = useState<Task | undefined>();
  const [activeTask, setActiveTask] = useState<Task | null>(null);

  const { data, isLoading, isError, error, refetch, isFetching } = useTasks({ projectId, page_size: 100 });
  const createMutation = useCreateTask(projectId);
  const updateMutation = useUpdateTask();
  const deleteMutation = useDeleteTask(projectId);
  const reorderMutation = useReorderTasks(projectId);

  const tasks = data?.items ?? [];

  // DnD is disabled when parent project is archived (read-only)
  const isDragDisabled = readOnly;

  // ─── Sensors ────────────────────────────────────────────────────────
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const taskIds = useMemo(() => tasks.map((t) => t.id), [tasks]);

  // ─── Drag handlers ─────────────────────────────────────────────────
  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      const task = tasks.find((t) => t.id === event.active.id);
      setActiveTask(task ?? null);
    },
    [tasks],
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      setActiveTask(null);

      const { active, over } = event;
      if (!over || active.id === over.id) return;

      const oldIndex = tasks.findIndex((t) => t.id === active.id);
      const newIndex = tasks.findIndex((t) => t.id === over.id);
      if (oldIndex === -1 || newIndex === -1) return;

      const reordered = arrayMove(tasks, oldIndex, newIndex);
      const items = reordered.map((t, idx) => ({ task_id: t.id, sort_order: idx + 1 }));

      reorderMutation.mutate(items, {
        onError: () => {
          toast({ variant: 'danger', message: 'Failed to reorder tasks. Order has been reverted.' });
        },
      });
    },
    [tasks, reorderMutation, toast],
  );

  const handleDragCancel = useCallback(() => {
    setActiveTask(null);
  }, []);

  // ─── Budget summary ────────────────────────────────────────────────
  // Coerce with Number() before summing: numeric columns can reach the client
  // as strings, and `0 + "500"` concatenates into "0500" rather than adding.
  const totalTaskBudget = useMemo(
    () => tasks.reduce((sum, t) => sum + (Number(t.budget_estimate) || 0), 0),
    [tasks],
  );
  const projectBudgetNum = projectBudget != null ? Number(projectBudget) : null;
  const budgetRemaining = projectBudgetNum != null ? projectBudgetNum - totalTaskBudget : null;
  const isOverBudget = budgetRemaining != null && budgetRemaining < 0;

  // ─── Loading / Error ───────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton height="40px" />
        <Skeleton height="200px" />
      </div>
    );
  }

  if (isError) {
    return (
      <Alert variant="danger" title="Could not load tasks">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span>{errorMessage(error, 'Could not fetch tasks for this project.')}</span>
          <Button variant="outline" size="sm" onClick={() => refetch()} isLoading={isFetching}>
            Retry
          </Button>
        </div>
      </Alert>
    );
  }

  // ─── CRUD handlers ─────────────────────────────────────────────────
  const handleCreate = (formData: Record<string, unknown>) => {
    createMutation.mutate(formData as unknown as Parameters<typeof createMutation.mutate>[0], {
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
        toast({ variant: 'danger', message: errorMessage(err, 'Failed to delete task. It may have active bids, awards, or contracts.') });
      },
    });
  };

  const handleRowClick = (task: Task) => {
    navigate(`/projects/${projectId}/tasks/${task.id}`);
  };

  // Find the index of the active (dragging) task for overlay
  const activeIndex = activeTask ? tasks.findIndex((t) => t.id === activeTask.id) : -1;

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
        {!readOnly && <Button onClick={() => setShowCreateForm(true)}>Add Task</Button>}
      </div>

      {isOverBudget && (
        <Alert variant="warning" title="Over Budget">
          Task budget estimates exceed the project budget by {formatCurrency(Math.abs(budgetRemaining!))}.
        </Alert>
      )}

      {/* Task list with drag-and-drop */}
      {tasks.length === 0 ? (
        <EmptyState
          title="No tasks yet"
          description="Create your first task to start building the bid pipeline for this project."
        />
      ) : (
        <Card>
          <div className="overflow-x-auto">
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragStart={handleDragStart}
              onDragEnd={handleDragEnd}
              onDragCancel={handleDragCancel}
            >
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
                <SortableContext items={taskIds} strategy={verticalListSortingStrategy}>
                  <tbody className="divide-y divide-secondary-100">
                    {tasks.map((task, idx) => (
                      <SortableTaskRow
                        key={task.id}
                        task={task}
                        index={idx}
                        isDragDisabled={isDragDisabled}
                        onRowClick={handleRowClick}
                        onEdit={setEditTask}
                        onDelete={setDeleteTarget}
                        readOnly={readOnly}
                      />
                    ))}
                  </tbody>
                </SortableContext>
              </table>

              <DragOverlay dropAnimation={null}>
                {activeTask && (
                  <TaskRowOverlay task={activeTask} index={activeIndex} />
                )}
              </DragOverlay>
            </DndContext>
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
      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="Delete Task"
        message={
          <>
            Are you sure you want to delete <strong>{deleteTarget?.name}</strong>? This
            soft-deletes the task and it will no longer appear in lists.
          </>
        }
        confirmText="Delete Task"
        isLoading={deleteMutation.isPending}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(undefined)}
      />
    </div>
  );
}
