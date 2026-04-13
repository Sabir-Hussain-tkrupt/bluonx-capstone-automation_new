import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { StatusBadge } from '@/components/ui/StatusBadge';
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

// ─── Grip (drag handle) icon ──────────────────────────────────────────
function GripVerticalIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
      <path d="M7 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM7 14a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 2a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 8a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM13 14a2 2 0 1 0 0 4 2 2 0 0 0 0-4z" />
    </svg>
  );
}

interface SortableTaskRowProps {
  task: Task;
  index: number;
  isDragDisabled: boolean;
  onRowClick: (task: Task) => void;
  onEdit: (task: Task) => void;
  onDelete: (task: Task) => void;
  readOnly?: boolean;
}

export function SortableTaskRow({ task, index, isDragDisabled, onRowClick, onEdit, onDelete, readOnly = false }: SortableTaskRowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.id, disabled: isDragDisabled });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
    zIndex: isDragging ? 10 : undefined,
    position: isDragging ? 'relative' as const : undefined,
  };

  return (
    <tr
      ref={setNodeRef}
      style={style}
      {...attributes}
      className="hover:bg-secondary-50 cursor-pointer transition-colors"
      onClick={() => onRowClick(task)}
    >
      {/* # column with drag handle */}
      <td className="px-4 py-3 text-secondary-400">
        <div className="flex items-center gap-1.5">
          {!isDragDisabled ? (
            <button
              ref={setActivatorNodeRef}
              {...listeners}
              type="button"
              className="cursor-grab touch-none rounded p-0.5 text-secondary-300 hover:text-secondary-500 hover:bg-secondary-100 active:cursor-grabbing"
              title="Drag to reorder"
              onClick={(e) => e.stopPropagation()}
            >
              <GripVerticalIcon className="h-4 w-4" />
            </button>
          ) : (
            <span className="inline-block w-5" />
          )}
          {index + 1}
        </div>
      </td>
      <td className="px-4 py-3 font-medium text-secondary-900">{task.name}</td>
      <td className="px-4 py-3 text-secondary-600 hidden md:table-cell">{task.trade_name ?? '\u2014'}</td>
      <td className="px-4 py-3 text-secondary-600 hidden lg:table-cell">{formatPhase(task.phase)}</td>
      <td className="px-4 py-3 text-secondary-600 hidden lg:table-cell">{formatBidType(task.bid_type)}</td>
      <td className="px-4 py-3"><StatusBadge status={task.status} size="sm" /></td>
      <td className="px-4 py-3 text-secondary-600 hidden sm:table-cell text-right">{formatCurrency(task.budget_estimate)}</td>
      <td className="px-4 py-3 text-right">
        {!readOnly && (
          <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="rounded p-1 text-secondary-400 hover:bg-secondary-100 hover:text-secondary-600"
              title="Edit task"
              onClick={() => onEdit(task)}
            >
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path d="M2.695 14.763l-1.262 3.154a.5.5 0 00.65.65l3.155-1.262a4 4 0 001.343-.885L17.5 5.5a2.121 2.121 0 00-3-3L3.58 13.42a4 4 0 00-.885 1.343z" />
              </svg>
            </button>
            <button
              type="button"
              className="rounded p-1 text-secondary-400 hover:bg-danger-50 hover:text-danger-600"
              title="Delete task"
              onClick={() => onDelete(task)}
            >
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        )}
      </td>
    </tr>
  );
}

// ─── Overlay row (shown while dragging) ─────────────────────────────
export function TaskRowOverlay({ task, index }: { task: Task; index: number }) {
  return (
    <table className="w-full text-left text-sm">
      <tbody>
        <tr className="bg-white shadow-lg ring-2 ring-primary-300 rounded">
          <td className="px-4 py-3 text-secondary-400">
            <div className="flex items-center gap-1.5">
              <GripVerticalIcon className="h-4 w-4 text-primary-500" />
              {index + 1}
            </div>
          </td>
          <td className="px-4 py-3 font-medium text-secondary-900">{task.name}</td>
          <td className="px-4 py-3 text-secondary-600 hidden md:table-cell">{task.trade_name ?? '\u2014'}</td>
          <td className="px-4 py-3 text-secondary-600 hidden lg:table-cell">{formatPhase(task.phase)}</td>
          <td className="px-4 py-3 text-secondary-600 hidden lg:table-cell">{formatBidType(task.bid_type)}</td>
          <td className="px-4 py-3"><StatusBadge status={task.status} size="sm" /></td>
          <td className="px-4 py-3 text-secondary-600 hidden sm:table-cell text-right">{formatCurrency(task.budget_estimate)}</td>
          <td className="px-4 py-3" />
        </tr>
      </tbody>
    </table>
  );
}
