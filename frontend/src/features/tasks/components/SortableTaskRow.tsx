import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, Pencil, Trash2 } from 'lucide-react';
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
  return <GripVertical className={className} aria-hidden="true" />;
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
              <Pencil className="h-4 w-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              className="rounded p-1 text-secondary-400 hover:bg-danger-50 hover:text-danger-600"
              title="Delete task"
              onClick={() => onDelete(task)}
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
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
