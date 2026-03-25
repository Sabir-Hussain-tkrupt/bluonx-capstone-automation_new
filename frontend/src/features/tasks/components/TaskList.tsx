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
import { Modal } from '@/components/ui/Modal';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';
import { useToast } from '@/components/ui/Toast/useToast';
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
}

export function TaskList({ projectId, projectBudget }: TaskListProps) {
  const navigate = useNavigate();
  const { toast } = useToast();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editTask, setEditTask] = useState<Task | undefined>();
  const [deleteTarget, setDeleteTarget] = useState<Task | undefined>();
  const [activeTask, setActiveTask] = useState<Task | null>(null);

  const { data, isLoading, error } = useTasks({ projectId, page_size: 100 });
  const createMutation = useCreateTask(projectId);
  const updateMutation = useUpdateTask();
  const deleteMutation = useDeleteTask(projectId);
  const reorderMutation = useReorderTasks(projectId);

  const tasks = data?.items ?? [];

  // DnD is only enabled in default sort_order view (no custom sort/search)
  const isDragDisabled = false; // Could be extended: set true when sort/filter is active

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
  const totalTaskBudget = useMemo(
    () => tasks.reduce((sum, t) => sum + (t.budget_estimate ?? 0), 0),
    [tasks],
  );
  const budgetRemaining = projectBudget != null ? projectBudget - totalTaskBudget : null;
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

  if (error) {
    return <Alert variant="danger" title="Failed to load tasks">Could not fetch tasks for this project.</Alert>;
  }

  // ─── CRUD handlers ─────────────────────────────────────────────────
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
        <Button onClick={() => setShowCreateForm(true)}>Add Task</Button>
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
