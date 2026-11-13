import { Fragment, useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowDown,
  ArrowUp,
  CornerDownRight,
  Landmark,
  Lock,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { DropdownMenu, DropdownMenuItem } from '@/components/ui/DropdownMenu';
import { IconButton } from '@/components/ui/IconButton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { formatDateOnly } from '@/lib/format';
import { CASH_BUCKET_LABELS, LINE_TYPE_LABELS } from '../constants';
import type { BudgetLine } from '../types';
import { formatCents, formatMoney, sumCents } from '../utils/money';

export interface BudgetTableActions {
  onEdit: (line: BudgetLine) => void;
  onMove: (line: BudgetLine, direction: -1 | 1) => void;
  onAddTmPortion: (line: BudgetLine) => void;
  onClosings: (line: BudgetLine) => void;
  onRemove: (line: BudgetLine) => void;
}

interface BudgetTableProps {
  projectId: string;
  lines: BudgetLine[];
  /** Admin and not archived: show the row action menu. */
  canEdit: boolean;
  actions: BudgetTableActions;
}

interface Section {
  name: string;
  lines: BudgetLine[];
}

/** Group lines by heading in budget order; variances follow their parent line. */
function buildSections(lines: BudgetLine[]): Section[] {
  const byParent = new Map<string, BudgetLine[]>();
  const top: BudgetLine[] = [];
  for (const line of lines) {
    if (line.line_type === 'variance' && line.parent_line_id) {
      byParent.set(line.parent_line_id, [...(byParent.get(line.parent_line_id) ?? []), line]);
    } else {
      top.push(line);
    }
  }
  const ordered: BudgetLine[] = [];
  for (const line of top) {
    ordered.push(line, ...(byParent.get(line.id) ?? []));
    byParent.delete(line.id);
  }
  for (const orphans of byParent.values()) ordered.push(...orphans);

  const sections: Section[] = [];
  for (const line of ordered) {
    const name = line.line_type === 'variance' ? sections.at(-1)?.name ?? 'Other' : line.section_name || 'Other';
    const last = sections.at(-1);
    if (last && last.name === name) last.lines.push(line);
    else sections.push({ name, lines: [line] });
  }
  return sections;
}

const TH = 'px-4 py-3 font-medium text-secondary-500';
const NUM = 'px-4 py-3 text-right tabular-nums';

export function BudgetTable({ projectId, lines, canEdit, actions }: BudgetTableProps) {
  const sections = useMemo(() => buildSections(lines), [lines]);
  const movable = useMemo(() => lines.filter((l) => l.line_type !== 'variance'), [lines]);

  const totals = useMemo(
    () => ({
      budget: sumCents(lines.map((l) => l.budget_amount)),
      committed: sumCents(lines.filter((l) => l.line_type !== 'contingency').map((l) => l.committed)),
      spent: sumCents(lines.map((l) => l.spent)),
      remaining: sumCents(lines.map((l) => l.remaining)),
    }),
    [lines],
  );

  return (
    <Card>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-secondary-200">
              <th className={TH}>Line</th>
              <th className={`${TH} text-right`}>Budget</th>
              <th className={`${TH} hidden text-right md:table-cell`}>Committed</th>
              <th className={`${TH} hidden text-right lg:table-cell`}>Spent</th>
              <th className={`${TH} text-right`}>Remaining</th>
              <th className={`${TH} hidden xl:table-cell`}>Dates</th>
              <th className={`${TH} hidden xl:table-cell`}>Terms</th>
              <th className={`${TH} hidden lg:table-cell`}>Bucket</th>
              {canEdit && <th className={`${TH} text-right`}>Actions</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-secondary-100">
            {sections.map((section, sIdx) => {
              const subtotal = sumCents(section.lines.map((l) => l.budget_amount));
              return (
                <Fragment key={`${section.name}-${sIdx}`}>
                  <tr className="bg-secondary-50">
                    <td colSpan={canEdit ? 9 : 8} className="px-4 py-2 text-xs font-semibold uppercase tracking-wider text-secondary-500">
                      {section.name}
                    </td>
                  </tr>
                  {section.lines.map((line) => {
                    const idx = movable.findIndex((m) => m.id === line.id);
                    return (
                      <BudgetRow
                        key={line.id}
                        projectId={projectId}
                        line={line}
                        canEdit={canEdit}
                        canMoveUp={idx > 0}
                        canMoveDown={idx >= 0 && idx < movable.length - 1}
                        actions={actions}
                      />
                    );
                  })}
                  <tr>
                    <td className="px-4 py-2 text-right text-xs font-medium text-secondary-500">{section.name} subtotal</td>
                    <td className={`${NUM} py-2 text-xs font-semibold text-secondary-700`}>{formatCents(subtotal)}</td>
                    <td colSpan={canEdit ? 7 : 6} />
                  </tr>
                </Fragment>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-secondary-200 font-semibold text-secondary-900">
              <td className="px-4 py-3">Total</td>
              <td className={NUM}>{formatCents(totals.budget)}</td>
              <td className={`${NUM} hidden md:table-cell`}>{formatCents(totals.committed)}</td>
              <td className={`${NUM} hidden lg:table-cell`}>{formatCents(totals.spent)}</td>
              <td className={NUM}>{formatCents(totals.remaining)}</td>
              <td className="hidden xl:table-cell" />
              <td className="hidden xl:table-cell" />
              <td className="hidden lg:table-cell" />
              {canEdit && <td />}
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  );
}

interface BudgetRowProps {
  projectId: string;
  line: BudgetLine;
  canEdit: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  actions: BudgetTableActions;
}

function BudgetRow({ projectId, line, canEdit, canMoveUp, canMoveDown, actions }: BudgetRowProps) {
  const isVariance = line.line_type === 'variance';
  const isUnallocated = line.line_subtype === 'unallocated';
  const needsDates = !line.has_dates && !['contingency', 'land'].includes(line.line_type) && !isUnallocated;
  const contingencyNegative = line.line_type === 'contingency' && Number(line.budget_amount) < 0;
  const removable = !line.task_id && !['contingency', 'variance'].includes(line.line_type);
  const canHaveTm = ['bid_activity', 'soft_cost'].includes(line.line_type);

  return (
    <tr className="transition-colors hover:bg-secondary-50">
      <td className="px-4 py-3">
        <div className={`flex min-w-[220px] items-start gap-2 ${isVariance ? 'pl-6' : ''}`}>
          {isVariance && <CornerDownRight className="mt-0.5 h-4 w-4 shrink-0 text-secondary-400" aria-hidden="true" />}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-1.5">
              {line.task_id ? (
                <Link
                  to={`/projects/${projectId}/tasks/${line.task_id}`}
                  className="font-medium text-secondary-900 hover:text-primary-600 hover:underline"
                >
                  {line.name}
                </Link>
              ) : (
                <span className="font-medium text-secondary-900">{line.name}</span>
              )}
              {line.is_locked && (
                <Lock className="h-3.5 w-3.5 text-secondary-400" aria-label="Locked: contract executed" />
              )}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <StatusBadge
                status={isUnallocated ? 'Unallocated' : LINE_TYPE_LABELS[line.line_type]}
                variant={isUnallocated ? 'info' : 'neutral'}
                dot={false}
                size="sm"
              />
              {line.vendor_name && <span className="text-xs text-secondary-500">{line.vendor_name}</span>}
              {isVariance && line.variance_status && (
                <StatusBadge status={line.variance_status} size="sm" />
              )}
              {line.closings_count > 0 && (
                <span className="text-xs text-secondary-500">
                  {line.closings_count} closing{line.closings_count === 1 ? '' : 's'}
                </span>
              )}
              {needsDates && <span className="text-xs text-warning-600">Dates missing</span>}
            </div>
          </div>
        </div>
      </td>
      <td className={`${NUM} ${contingencyNegative ? 'font-semibold text-danger-600' : 'text-secondary-900'}`}>
        {formatMoney(line.budget_amount)}
      </td>
      <td className={`${NUM} hidden text-secondary-700 md:table-cell`}>
        {line.line_type === 'contingency' ? '—' : formatMoney(line.committed)}
      </td>
      <td className={`${NUM} hidden text-secondary-700 lg:table-cell`}>{formatMoney(line.spent)}</td>
      <td className={`${NUM} text-secondary-900`}>{line.remaining == null ? '—' : formatMoney(line.remaining)}</td>
      <td className="hidden whitespace-nowrap px-4 py-3 text-secondary-700 xl:table-cell">
        {line.has_dates
          ? `${formatDateOnly(line.anticipated_start_date)} – ${formatDateOnly(line.anticipated_end_date)}`
          : '—'}
      </td>
      <td className="hidden px-4 py-3 text-secondary-700 xl:table-cell">{line.payment_terms_days} days</td>
      <td className="hidden px-4 py-3 text-secondary-700 lg:table-cell">{CASH_BUCKET_LABELS[line.cash_bucket]}</td>
      {canEdit && (
        <td className="px-4 py-3 text-right">
          {!isVariance && (
            <DropdownMenu
              trigger={
                <IconButton
                  variant="ghost"
                  size="sm"
                  icon={<MoreHorizontal className="h-4 w-4" />}
                  aria-label={`Actions for ${line.name}`}
                />
              }
            >
              <DropdownMenuItem icon={<Pencil className="h-4 w-4" />} onClick={() => actions.onEdit(line)}>
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem icon={<ArrowUp className="h-4 w-4" />} disabled={!canMoveUp} onClick={() => actions.onMove(line, -1)}>
                Move up
              </DropdownMenuItem>
              <DropdownMenuItem icon={<ArrowDown className="h-4 w-4" />} disabled={!canMoveDown} onClick={() => actions.onMove(line, 1)}>
                Move down
              </DropdownMenuItem>
              {canHaveTm && (
                <DropdownMenuItem icon={<Plus className="h-4 w-4" />} onClick={() => actions.onAddTmPortion(line)}>
                  Add T&amp;M portion
                </DropdownMenuItem>
              )}
              {line.line_type === 'land' && (
                <DropdownMenuItem icon={<Landmark className="h-4 w-4" />} onClick={() => actions.onClosings(line)}>
                  Phased closings
                </DropdownMenuItem>
              )}
              {removable && (
                <DropdownMenuItem icon={<Trash2 className="h-4 w-4" />} destructive onClick={() => actions.onRemove(line)}>
                  Remove line
                </DropdownMenuItem>
              )}
            </DropdownMenu>
          )}
        </td>
      )}
    </tr>
  );
}
