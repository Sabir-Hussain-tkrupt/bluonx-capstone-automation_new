import { useMemo, useState } from 'react';
import { CornerDownRight, MoreHorizontal, Pencil, Plus, Trash2 } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { Modal } from '@/components/ui/Modal';
import { IconButton } from '@/components/ui/IconButton';
import { DropdownMenu, DropdownMenuItem } from '@/components/ui/DropdownMenu';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { useTrades } from '../hooks/useTrades';
import { useDeleteTrade, useTradeUsage } from '../hooks/useTradeMutations';
import { TRADE_PHASE_LABELS, TRADE_PHASE_ORDER } from '../types';
import type { Trade, TradePhase } from '../types';
import { buildTradeTree, type TradeNode } from '../utils/tradeTree';
import { CreateTradeModal } from './CreateTradeModal';
import { describeTradeUsage } from './tradeUsageText';

const phaseSubtitles: Record<TradePhase, string> = {
  due_diligence: 'Investigation work (geotech, surveys, environmental, etc.)',
  development: 'Construction work (grading, utilities, paving, etc.)',
  both: 'Trades used across both Due Diligence and Development phases.',
};

type FormState =
  | { kind: 'create' }
  | { kind: 'subtrade'; parent: Trade }
  | { kind: 'edit'; trade: Trade; parent: Trade | null };

// ── Delete (checks usage first) ─────────────────────────────────────────

function DeleteTradeDialog({ trade, isSubtrade, onClose }: { trade: Trade; isSubtrade: boolean; onClose: () => void }) {
  const { toast } = useToast();
  const usage = useTradeUsage(trade.id);
  const remove = useDeleteTrade();
  const kind = isSubtrade ? 'subtrade' : 'trade';
  const blocked = usage.data ? !usage.data.can_delete : false;

  const confirm = () =>
    remove.mutate(trade.id, {
      onSuccess: () => {
        toast({ variant: 'success', message: `${trade.name} has been deleted.` });
        onClose();
      },
      onError: (error) => toast({ variant: 'danger', message: errorMessage(error, `Could not delete the ${kind}.`) }),
    });

  return (
    <Modal
      isOpen
      onClose={() => !remove.isPending && onClose()}
      title={blocked ? `Cannot delete ${kind}` : `Delete ${kind}?`}
      size="sm"
      footer={
        blocked || usage.isError ? (
          <Button variant="outline" onClick={onClose}>Close</Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose} disabled={remove.isPending}>Cancel</Button>
            <Button variant="danger" onClick={confirm} isLoading={remove.isPending} disabled={usage.isLoading}>
              Delete
            </Button>
          </>
        )
      }
    >
      {usage.isLoading ? (
        <div className="space-y-2" aria-label="Checking usage">
          <Skeleton variant="text" />
          <Skeleton variant="text" width="70%" />
        </div>
      ) : usage.isError ? (
        <Alert variant="danger" title="Could not check where this trade is used">
          {errorMessage(usage.error, 'Please try again.')}
        </Alert>
      ) : blocked && usage.data ? (
        <div className="space-y-3 text-sm text-secondary-700">
          <p>
            <span className="font-medium text-secondary-900">{trade.name}</span> is used by{' '}
            {describeTradeUsage(usage.data)}, so it cannot be deleted.
          </p>
          <p className="text-secondary-500">
            {usage.data.subtrades > 0 && !usage.data.in_use
              ? 'Delete its subtrades first.'
              : `Remove it from those records first, or keep the ${kind}.`}
          </p>
        </div>
      ) : (
        <p className="text-sm text-secondary-700">
          <span className="font-medium text-secondary-900">{trade.name}</span> is not used anywhere and will be
          permanently deleted.
        </p>
      )}
    </Modal>
  );
}

// ── Rows ────────────────────────────────────────────────────────────────

interface RowActions {
  onAddSubtrade: (parent: Trade) => void;
  onEdit: (trade: Trade, parent: Trade | null) => void;
  onDelete: (trade: Trade, isSubtrade: boolean) => void;
}

function TradeRow({ node, actions }: { node: TradeNode<Trade>; actions: RowActions }) {
  const { trade, children } = node;
  return (
    <li className="py-1.5">
      <div className="flex items-center justify-between gap-2 text-sm text-secondary-800">
        <span className="min-w-0 truncate font-medium">
          {trade.name}
          {children.length > 0 && (
            <span className="ml-2 text-xs font-normal text-secondary-400">
              {children.length} subtrade{children.length === 1 ? '' : 's'}
            </span>
          )}
        </span>
        <DropdownMenu
          trigger={<IconButton icon={<MoreHorizontal className="h-4 w-4" />} aria-label={`Actions for ${trade.name}`} variant="ghost" size="sm" />}
          align="right"
        >
          <DropdownMenuItem icon={<Plus className="h-4 w-4" />} onClick={() => actions.onAddSubtrade(trade)}>
            Add subtrade
          </DropdownMenuItem>
          <DropdownMenuItem icon={<Pencil className="h-4 w-4" />} onClick={() => actions.onEdit(trade, null)}>
            Edit
          </DropdownMenuItem>
          <DropdownMenuItem icon={<Trash2 className="h-4 w-4" />} destructive onClick={() => actions.onDelete(trade, false)}>
            Delete
          </DropdownMenuItem>
        </DropdownMenu>
      </div>
      {children.length > 0 && (
        <ul className="mt-1 space-y-0.5 border-l border-secondary-200 pl-3" aria-label={`Subtrades of ${trade.name}`}>
          {children.map((sub) => (
            <li key={sub.id} className="flex items-center justify-between gap-2 text-sm text-secondary-700">
              <span className="flex min-w-0 items-center gap-1.5">
                <CornerDownRight className="h-3.5 w-3.5 shrink-0 text-secondary-300" aria-hidden="true" />
                <span className="truncate">{sub.name}</span>
              </span>
              <DropdownMenu
                trigger={<IconButton icon={<MoreHorizontal className="h-4 w-4" />} aria-label={`Actions for ${sub.name}`} variant="ghost" size="sm" />}
                align="right"
              >
                <DropdownMenuItem icon={<Pencil className="h-4 w-4" />} onClick={() => actions.onEdit(sub, trade)}>
                  Edit
                </DropdownMenuItem>
                <DropdownMenuItem icon={<Trash2 className="h-4 w-4" />} destructive onClick={() => actions.onDelete(sub, true)}>
                  Delete
                </DropdownMenuItem>
              </DropdownMenu>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

// ── Panel ───────────────────────────────────────────────────────────────

export function TradeManagementPanel() {
  const { data, isLoading, isError, error, refetch } = useTrades();
  const [form, setForm] = useState<FormState | null>(null);
  const [formKey, setFormKey] = useState(0);
  const [deleting, setDeleting] = useState<{ trade: Trade; isSubtrade: boolean } | null>(null);

  const grouped = useMemo(() => {
    const buckets: Record<TradePhase, TradeNode<Trade>[]> = {
      due_diligence: [],
      development: [],
      both: [],
    };
    for (const node of buildTradeTree(data ?? [])) {
      buckets[node.trade.phase]?.push(node);
    }
    return buckets;
  }, [data]);

  const topLevelCount = useMemo(() => (data ?? []).filter((t) => !t.parent_trade_id).length, [data]);
  const subtradeCount = (data?.length ?? 0) - topLevelCount;

  const open = (next: FormState) => {
    setFormKey((k) => k + 1);
    setForm(next);
  };

  const actions: RowActions = {
    onAddSubtrade: (parent) => open({ kind: 'subtrade', parent }),
    onEdit: (trade, parent) => open({ kind: 'edit', trade, parent }),
    onDelete: (trade, isSubtrade) => setDeleting({ trade, isSubtrade }),
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-secondary-500">
          {data
            ? `${topLevelCount} active trade${topLevelCount === 1 ? '' : 's'}${subtradeCount ? ` and ${subtradeCount} subtrade${subtradeCount === 1 ? '' : 's'}` : ''} across all phases.`
            : 'Loading trades…'}
        </p>
        <Button onClick={() => open({ kind: 'create' })} leftIcon={<Plus className="h-4 w-4" aria-hidden="true" />}>
          New Trade
        </Button>
      </div>

      {isError && (
        <Alert
          variant="danger"
          title="Could not load trades"
          dismissible
          onDismiss={() => refetch()}
        >
          {errorMessage(error, 'Please try again.')}
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {TRADE_PHASE_ORDER.map((phase) => (
          <Card key={phase} title={TRADE_PHASE_LABELS[phase]} subtitle={phaseSubtitles[phase]}>
            {isLoading ? (
              <div className="space-y-2">
                <Skeleton variant="rectangular" height="32px" />
                <Skeleton variant="rectangular" height="32px" />
                <Skeleton variant="rectangular" height="32px" />
              </div>
            ) : grouped[phase].length === 0 ? (
              <EmptyState
                title="No trades yet"
                description={`No trades configured for ${TRADE_PHASE_LABELS[phase].toLowerCase()}.`}
              />
            ) : (
              <ul className="divide-y divide-secondary-100">
                {grouped[phase].map((node) => (
                  <TradeRow key={node.trade.id} node={node} actions={actions} />
                ))}
              </ul>
            )}
          </Card>
        ))}
      </div>

      {form && (
        <CreateTradeModal
          key={formKey}
          isOpen
          onClose={() => setForm(null)}
          parent={form.kind === 'subtrade' ? form.parent : null}
          trade={form.kind === 'edit' ? form.trade : null}
          tradeParent={form.kind === 'edit' ? form.parent : null}
        />
      )}

      {deleting && (
        <DeleteTradeDialog
          key={deleting.trade.id}
          trade={deleting.trade}
          isSubtrade={deleting.isSubtrade}
          onClose={() => setDeleting(null)}
        />
      )}
    </div>
  );
}
