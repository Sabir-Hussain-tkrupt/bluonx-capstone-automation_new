import { useCallback, useMemo, useState } from 'react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, Pencil, Trash2 } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { CASH_BUCKET_LABELS, LINE_TYPE_LABELS } from '@/features/budgets/constants';
import { useDefaultBudgetTemplate, useDeleteTemplateLine, useReorderTemplateLines } from '@/features/budgets/hooks/useBudget';
import type { BudgetTemplateLine } from '@/features/budgets/types';
import { formatMoney } from '@/features/budgets/utils/money';
import { TemplateLineModal } from '../components/TemplateLineModal';

/**
 * Settings → Budget Template (Task 2.1). One standard layout, from land
 * acquisition down to escrows and property taxes, copied into every new project
 * budget. Editing it never changes existing budgets.
 */
export function BudgetTemplatePage() {
  const { toast } = useToast();
  const { data, isLoading, isError, error, refetch } = useDefaultBudgetTemplate();
  const template = data?.template ?? null;
  const lines = useMemo(() => data?.lines ?? [], [data]);
  const reorder = useReorderTemplateLines(template?.id ?? '');
  const deleteLine = useDeleteTemplateLine();

  const [editing, setEditing] = useState<BudgetTemplateLine | null>(null);
  const [adding, setAdding] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<BudgetTemplateLine | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;
      const from = lines.findIndex((l) => l.id === active.id);
      const to = lines.findIndex((l) => l.id === over.id);
      if (from < 0 || to < 0) return;
      reorder.mutate(arrayMove(lines, from, to).map((l) => l.id), {
        onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Failed to reorder. Order has been reverted.') }),
      });
    },
    [lines, reorder, toast],
  );

  const handleDelete = () => {
    if (!deleteTarget) return;
    deleteLine.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast({ variant: 'success', message: `${deleteTarget.name} removed from the template.` });
        setDeleteTarget(null);
      },
      onError: (e) => {
        toast({ variant: 'danger', message: errorMessage(e, 'Could not remove the line.') });
        setDeleteTarget(null);
      },
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-secondary-900">Budget Template</h1>
          <p className="mt-1 max-w-2xl text-sm text-secondary-500">
            The standard layout every new project budget starts from. Activity rows (bid / internal) are placeholders:
            tasks with the same name or trade are placed there. Changes apply to new budgets only.
          </p>
        </div>
        {template && <Button onClick={() => setAdding(true)}>Add line</Button>}
      </div>

      {isLoading && <Skeleton height="320px" />}

      {isError && (
        <Alert variant="danger" title="Could not load the template">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>{errorMessage(error, 'Something went wrong. Please try again.')}</span>
            <Button variant="outline" size="sm" onClick={() => refetch()}>Retry</Button>
          </div>
        </Alert>
      )}

      {!isLoading && !isError && !template && (
        <EmptyState title="No standard template" description="Apply the Phase 2 database migration to create the default template." />
      )}

      {template && (
        <Card>
          {lines.length === 0 ? (
            <EmptyState title="The template is empty" description="Add the first line." />
          ) : (
            <div className="overflow-x-auto">
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-secondary-200">
                      <th className="px-4 py-3 font-medium text-secondary-500">#</th>
                      <th className="px-4 py-3 font-medium text-secondary-500">Line</th>
                      <th className="px-4 py-3 font-medium text-secondary-500">Type</th>
                      <th className="hidden px-4 py-3 font-medium text-secondary-500 md:table-cell">Heading</th>
                      <th className="hidden px-4 py-3 text-right font-medium text-secondary-500 lg:table-cell">Default amount</th>
                      <th className="hidden px-4 py-3 font-medium text-secondary-500 lg:table-cell">Bucket</th>
                      <th className="px-4 py-3 text-right font-medium text-secondary-500">Actions</th>
                    </tr>
                  </thead>
                  <SortableContext items={lines.map((l) => l.id)} strategy={verticalListSortingStrategy}>
                    <tbody className="divide-y divide-secondary-100">
                      {lines.map((line, i) => (
                        <TemplateRow key={line.id} line={line} index={i} onEdit={setEditing} onDelete={setDeleteTarget} />
                      ))}
                    </tbody>
                  </SortableContext>
                </table>
              </DndContext>
            </div>
          )}
        </Card>
      )}

      {template && (
        <TemplateLineModal
          templateId={template.id}
          isOpen={adding || !!editing}
          line={editing}
          onClose={() => {
            setAdding(false);
            setEditing(null);
          }}
        />
      )}

      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="Remove template line"
        message={<>Remove <strong>{deleteTarget?.name}</strong> from the template? Existing project budgets are not affected.</>}
        confirmText="Remove"
        isLoading={deleteLine.isPending}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

function TemplateRow({
  line,
  index,
  onEdit,
  onDelete,
}: {
  line: BudgetTemplateLine;
  index: number;
  onEdit: (l: BudgetTemplateLine) => void;
  onDelete: (l: BudgetTemplateLine) => void;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id: line.id });
  const isActivity = line.line_type === 'bid_activity' || line.line_type === 'internal_tm';
  return (
    <tr
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.4 : 1 }}
      {...attributes}
      className="transition-colors hover:bg-secondary-50"
    >
      <td className="px-4 py-3 text-secondary-400">
        <div className="flex items-center gap-1.5">
          <button
            ref={setActivatorNodeRef}
            {...listeners}
            type="button"
            className="cursor-grab touch-none rounded p-0.5 text-secondary-300 hover:bg-secondary-100 hover:text-secondary-500 active:cursor-grabbing"
            title="Drag to reorder"
          >
            <GripVertical className="h-4 w-4" aria-hidden="true" />
          </button>
          {index + 1}
        </div>
      </td>
      <td className="px-4 py-3 font-medium text-secondary-900">
        {line.name}
        {isActivity && <span className="ml-2 text-xs font-normal text-secondary-500">(task slot)</span>}
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={LINE_TYPE_LABELS[line.line_type]} variant="neutral" dot={false} size="sm" />
      </td>
      <td className="hidden px-4 py-3 text-secondary-600 md:table-cell">{line.section_name ?? '—'}</td>
      <td className="hidden px-4 py-3 text-right tabular-nums text-secondary-600 lg:table-cell">
        {line.default_amount != null ? formatMoney(line.default_amount) : '—'}
      </td>
      <td className="hidden px-4 py-3 text-secondary-600 lg:table-cell">
        {line.default_cash_bucket ? CASH_BUCKET_LABELS[line.default_cash_bucket] : '—'}
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex justify-end gap-1">
          <button type="button" className="rounded p-1 text-secondary-400 hover:bg-secondary-100 hover:text-secondary-600"
            title="Edit line" onClick={() => onEdit(line)}>
            <Pencil className="h-4 w-4" aria-hidden="true" />
          </button>
          <button type="button" className="rounded p-1 text-secondary-400 hover:bg-danger-50 hover:text-danger-600"
            title="Remove line" onClick={() => onDelete(line)}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </td>
    </tr>
  );
}
