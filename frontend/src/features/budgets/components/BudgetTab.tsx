import { useState } from 'react';
import { Download, MoreHorizontal, Plus, RefreshCw, RotateCcw, Upload } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { DropdownMenu, DropdownMenuItem } from '@/components/ui/DropdownMenu';
import { EmptyState } from '@/components/ui/EmptyState';
import { FormField } from '@/components/ui/FormField';
import { IconButton } from '@/components/ui/IconButton';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { useHasRole } from '@/lib/roles';
import { exportBudget } from '../api/budget.api';
import {
  useBaselineBudget,
  useBudgetLines,
  useBudgetSummary,
  useCreateBudget,
  useRemoveBudgetLine,
  useReorderBudgetLines,
  useResetBudget,
  useSyncAwards,
} from '../hooks/useBudget';
import type { BudgetLine } from '../types';
import { formatCents, formatMoney, toCents } from '../utils/money';
import { BidVsBudgetView } from './BidVsBudgetView';
import { BudgetImportModal } from './BudgetImportModal';
import { BudgetLineFormModal } from './BudgetLineFormModal';
import { BudgetSummaryCards } from './BudgetSummaryCards';
import { BudgetTable } from './BudgetTable';
import { LandClosingsModal } from './LandClosingsModal';

interface BudgetTabProps {
  projectId: string;
  readOnly?: boolean;
}

type View = 'lines' | 'bid_vs_budget';

/**
 * Task 2.4 — the project Budget tab. Only admins create and edit budgets (the
 * same rule as today's project budget field); everyone else sees the same
 * screen read-only, with the edit controls hidden.
 */
export function BudgetTab({ projectId, readOnly = false }: BudgetTabProps) {
  const { toast } = useToast();
  const isAdmin = useHasRole('admin');
  const canEdit = isAdmin && !readOnly;

  const summaryQuery = useBudgetSummary(projectId);
  const linesQuery = useBudgetLines(projectId);
  const createBudget = useCreateBudget(projectId);
  const baselineBudget = useBaselineBudget(projectId);
  const syncAwards = useSyncAwards(projectId);
  const resetBudget = useResetBudget(projectId);
  const removeLine = useRemoveBudgetLine(projectId);
  const reorderLines = useReorderBudgetLines(projectId);

  const [view, setView] = useState<View>('lines');
  const [showCreate, setShowCreate] = useState(false);
  const [contingencyPct, setContingencyPct] = useState('');
  const [showBaseline, setShowBaseline] = useState(false);
  const [showReset, setShowReset] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [formState, setFormState] = useState<{ line?: BudgetLine; parent?: BudgetLine } | null>(null);
  const [closingsLine, setClosingsLine] = useState<BudgetLine | null>(null);
  const [removeTarget, setRemoveTarget] = useState<BudgetLine | null>(null);
  const [exporting, setExporting] = useState(false);

  const summary = summaryQuery.data;
  const lines = linesQuery.data ?? [];
  const status = summary?.budget_status ?? 'none';

  // Preview for the Create dialog: total = the project's Budget value, and
  // contingency = pct of the base where base = total - land - contingency
  // (land is $0 before the budget exists), i.e. total x pct / (100 + pct).
  const pctInput = contingencyPct.trim() === '' ? 15 : Number(contingencyPct);
  const createPreview =
    summary?.project_budget != null && Number(summary.project_budget) > 0 && Number.isFinite(pctInput)
      ? {
          total: toCents(summary.project_budget),
          pct: pctInput,
          contingency: Math.round((toCents(summary.project_budget) * pctInput) / (100 + pctInput)),
        }
      : null;

  if (summaryQuery.isLoading || linesQuery.isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton height="96px" />
        <Skeleton height="320px" />
      </div>
    );
  }

  if (summaryQuery.isError || linesQuery.isError) {
    return (
      <Alert variant="danger" title="Could not load the budget">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span>{errorMessage(summaryQuery.error ?? linesQuery.error, 'Something went wrong. Please try again.')}</span>
          <Button variant="outline" size="sm" onClick={() => { summaryQuery.refetch(); linesQuery.refetch(); }}>
            Retry
          </Button>
        </div>
      </Alert>
    );
  }

  // ─── Handlers ───────────────────────────────────────────────────────
  const handleCreate = () => {
    const pct = contingencyPct.trim();
    if (pct && (!/^\d{1,3}(\.\d{1,2})?$/.test(pct) || Number(pct) > 100)) {
      toast({ variant: 'danger', message: 'Contingency % must be a number between 0 and 100.' });
      return;
    }
    createBudget.mutate(pct ? { contingency_percent: pct } : {}, {
      onSuccess: (res) => {
        setShowCreate(false);
        toast({ variant: 'success', message: `Budget created with ${res.line_count} lines.` });
      },
      onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not create the budget.') }),
    });
  };

  const handleBaseline = () => {
    baselineBudget.mutate(undefined, {
      onSuccess: () => {
        setShowBaseline(false);
        toast({ variant: 'success', message: 'Budget baselined. The total is now flat.' });
      },
      onError: (e) => {
        setShowBaseline(false);
        toast({ variant: 'danger', message: errorMessage(e, 'Could not baseline the budget.') });
      },
    });
  };

  const handleReset = () => {
    resetBudget.mutate(undefined, {
      onSuccess: () => {
        setShowReset(false);
        toast({ variant: 'success', message: 'Draft budget reset. Create it again to rebuild it from the template.' });
      },
      onError: (e) => {
        setShowReset(false);
        toast({ variant: 'danger', message: errorMessage(e, 'Could not reset the budget.') });
      },
    });
  };

  const handleSync = () => {
    syncAwards.mutate(undefined, {
      onSuccess: (r) =>
        toast({
          variant: r.failed ? 'warning' : 'success',
          message: `Awards synced: ${r.applied} applied, ${r.locked} locked${r.failed ? `, ${r.failed} need attention` : ''}.`,
        }),
      onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not sync awards.') }),
    });
  };

  const handleExport = async (format: 'xlsx' | 'csv') => {
    setExporting(true);
    try {
      await exportBudget(projectId, format);
    } catch (e) {
      toast({ variant: 'danger', message: errorMessage(e, 'Could not export the budget.') });
    } finally {
      setExporting(false);
    }
  };

  const handleMove = (line: BudgetLine, direction: -1 | 1) => {
    const ordered = lines.map((l) => l.id);
    const movable = lines.filter((l) => l.line_type !== 'variance').map((l) => l.id);
    const i = movable.indexOf(line.id);
    const swapWith = movable[i + direction];
    if (i < 0 || !swapWith) return;
    const a = ordered.indexOf(line.id);
    const b = ordered.indexOf(swapWith);
    [ordered[a], ordered[b]] = [ordered[b], ordered[a]];
    reorderLines.mutate(ordered, {
      onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not move the line.') }),
    });
  };

  const handleRemove = () => {
    if (!removeTarget) return;
    removeLine.mutate(removeTarget.id, {
      onSuccess: () => {
        toast({ variant: 'success', message: `${removeTarget.name} removed.` });
        setRemoveTarget(null);
      },
      onError: (e) => {
        toast({ variant: 'danger', message: errorMessage(e, 'Could not remove the line.') });
        setRemoveTarget(null);
      },
    });
  };

  // ─── No budget yet ──────────────────────────────────────────────────
  if (!summary || status === 'none') {
    return (
      <>
        <EmptyState
          title="No budget yet"
          description={
            canEdit
              ? 'Create the budget from the standard template. Every task on this project becomes a budget line.'
              : 'An admin has not created a budget for this project yet.'
          }
          action={canEdit ? <Button onClick={() => setShowCreate(true)}>Create budget</Button> : undefined}
        />
        <Modal
          isOpen={showCreate}
          onClose={() => !createBudget.isPending && setShowCreate(false)}
          title="Create budget"
          size="md"
          footer={
            <>
              <Button variant="ghost" onClick={() => setShowCreate(false)} disabled={createBudget.isPending}>Cancel</Button>
              <Button onClick={handleCreate} isLoading={createBudget.isPending}>Create budget</Button>
            </>
          }
        >
          <div className="space-y-4">
            <p className="text-sm text-secondary-600">
              The budget starts from the standard template (Settings → Budget Template). Every task becomes a line in
              template order. Tasks that are already awarded come in at their award amount as committed. You can add,
              remove, reorder and edit lines until you baseline.
            </p>
            {createPreview ? (
              <div className="rounded-lg border border-secondary-200 bg-secondary-50 px-3 py-2 text-sm text-secondary-700">
                <div className="flex justify-between">
                  <span>Total budget (project Budget value)</span>
                  <strong className="tabular-nums text-secondary-900">{formatCents(createPreview.total)}</strong>
                </div>
                <div className="flex justify-between">
                  <span>Contingency ({createPreview.pct}% of the base)</span>
                  <strong className="tabular-nums text-secondary-900">{formatCents(createPreview.contingency)}</strong>
                </div>
                <p className="mt-1 text-xs text-secondary-500">
                  Base = total − land − contingency. What is not assigned to a line yet sits on an “Unallocated” line.
                </p>
              </div>
            ) : (
              <Alert variant="info" title="No project budget set">
                This project has no Budget value, so the total will be the sum of the lines and contingency the % of
                that. Set a Budget on the project (Edit) to fix the total instead.
              </Alert>
            )}
            <FormField
              label="Contingency %"
              htmlFor="budget-contingency"
              hint="Leave empty for the default (15%). Contingency = this % of the budget excluding land."
            >
              <TextInput
                id="budget-contingency"
                inputMode="decimal"
                placeholder="15"
                value={contingencyPct}
                onChange={(e) => setContingencyPct(e.target.value)}
              />
            </FormField>
          </div>
        </Modal>
      </>
    );
  }

  // ─── Budget ─────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      <BudgetSummaryCards summary={summary} />

      {status === 'draft' ? (
        <Alert variant="info" title="Draft budget">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>
              Amounts can be changed until the budget is baselined. Baselining freezes the original estimates and
              keeps the total flat from then on.
            </span>
            {canEdit && (
              <Button size="sm" onClick={() => setShowBaseline(true)}>Baseline budget</Button>
            )}
          </div>
        </Alert>
      ) : (
        <Alert variant="neutral" title={`Baselined ${summary.approved_budget_total != null ? `at ${formatMoney(summary.approved_budget_total)}` : ''}`}>
          Changes now go through bids, variances and executive-approved top-ups, so the total budget stays flat.
        </Alert>
      )}

      {status === 'draft' && summary.over_project_budget != null && toCents(summary.over_project_budget) > 0 && (
        <Alert variant="warning" title="Lines exceed the project budget">
          The lines add up to {formatMoney(summary.total_budget)}, which is{' '}
          {formatMoney(summary.over_project_budget)} more than the project budget of {formatMoney(summary.project_budget)}.
          Lower some lines or raise the project Budget before baselining.
        </Alert>
      )}

      {summary.lines_missing_dates > 0 && (
        <Alert variant="warning" title={`${summary.lines_missing_dates} line${summary.lines_missing_dates === 1 ? '' : 's'} without dates`}>
          Lines need a start and end date to appear in cash flow.
        </Alert>
      )}

      {/* Toolbar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Button size="sm" variant={view === 'lines' ? 'primary' : 'outline'} onClick={() => setView('lines')}>
            Lines
          </Button>
          <Button size="sm" variant={view === 'bid_vs_budget' ? 'primary' : 'outline'} onClick={() => setView('bid_vs_budget')}>
            Bid vs Budget
          </Button>
          <StatusBadge status={status} variant={status === 'baselined' ? 'success' : 'info'} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canEdit && (
            <Button leftIcon={<Plus className="h-4 w-4" />} onClick={() => setFormState({})}>
              Add line
            </Button>
          )}
          {canEdit && status === 'draft' && (
            <Button variant="outline" leftIcon={<Download className="h-4 w-4" />} onClick={() => setShowImport(true)}>
              Import
            </Button>
          )}
          <DropdownMenu
            trigger={
              <Button variant="outline" leftIcon={<Upload className="h-4 w-4" />} isLoading={exporting}>
                Export
              </Button>
            }
          >
            <DropdownMenuItem onClick={() => handleExport('xlsx')}>Excel (.xlsx)</DropdownMenuItem>
            <DropdownMenuItem onClick={() => handleExport('csv')}>CSV</DropdownMenuItem>
          </DropdownMenu>
          {canEdit && (
            <DropdownMenu
              trigger={<IconButton variant="outline" icon={<MoreHorizontal className="h-4 w-4" />} aria-label="More budget actions" />}
            >
              <DropdownMenuItem icon={<RefreshCw className="h-4 w-4" />} onClick={handleSync}>
                Sync awards
              </DropdownMenuItem>
              {status === 'draft' && (
                <DropdownMenuItem icon={<RotateCcw className="h-4 w-4" />} destructive onClick={() => setShowReset(true)}>
                  Reset draft budget
                </DropdownMenuItem>
              )}
            </DropdownMenu>
          )}
        </div>
      </div>

      {view === 'lines' ? (
        lines.length === 0 ? (
          <EmptyState title="No lines" description="Add lines or tasks to build the budget." />
        ) : (
          <BudgetTable
            projectId={projectId}
            lines={lines}
            canEdit={canEdit}
            actions={{
              onEdit: (line) => setFormState({ line }),
              onMove: handleMove,
              onAddTmPortion: (parent) => setFormState({ parent }),
              onClosings: setClosingsLine,
              onRemove: setRemoveTarget,
            }}
          />
        )
      ) : (
        <BidVsBudgetView lines={lines} />
      )}

      <BudgetLineFormModal
        projectId={projectId}
        isOpen={formState !== null}
        onClose={() => setFormState(null)}
        budgetStatus={status}
        line={formState?.line ?? null}
        parentLine={formState?.parent ?? null}
      />

      <LandClosingsModal projectId={projectId} line={closingsLine} canEdit={canEdit} onClose={() => setClosingsLine(null)} />

      <BudgetImportModal projectId={projectId} isOpen={showImport} onClose={() => setShowImport(false)} />

      <ConfirmDialog
        isOpen={showBaseline}
        title="Baseline budget"
        message={
          <>
            Baseline this budget at <strong>{formatMoney(summary.total_budget)}</strong>? The original estimates are
            frozen and the total stays flat from now on: bid differences and field variances move money in and out of
            contingency, and only an executive-approved top-up can raise the total.
          </>
        }
        confirmText="Baseline budget"
        confirmVariant="primary"
        isLoading={baselineBudget.isPending}
        onConfirm={handleBaseline}
        onCancel={() => setShowBaseline(false)}
      />

      <ConfirmDialog
        isOpen={showReset}
        title="Reset draft budget"
        message={
          <>
            Start this draft budget over? All lines are removed (kept in the history) and the project returns to
            “no budget”. Create it again to rebuild it from the template, the project Budget value and the current
            awards.
          </>
        }
        confirmText="Reset budget"
        isLoading={resetBudget.isPending}
        onConfirm={handleReset}
        onCancel={() => setShowReset(false)}
      />

      <ConfirmDialog
        isOpen={!!removeTarget}
        title="Remove line"
        message={
          <>
            Remove <strong>{removeTarget?.name}</strong> from the budget? It is kept in the history but no longer counts
            toward totals.
          </>
        }
        confirmText="Remove line"
        isLoading={removeLine.isPending}
        onConfirm={handleRemove}
        onCancel={() => setRemoveTarget(null)}
      />
    </div>
  );
}
