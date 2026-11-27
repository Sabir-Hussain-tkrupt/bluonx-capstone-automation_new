import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatCard } from '@/components/ui/StatCard';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { errorMessage } from '@/lib/api';
import { formatDateOnly } from '@/lib/format';
import { formatMoney, toCents } from '@/features/budgets/utils/money';
import { BENEFICIARY_LABELS, ESCROW_STATUS, TAX_STATUS } from '../constants';
import { useJurisdictions, useLongTail } from '../hooks/useLongTail';
import type { Jurisdiction, PropertyTax } from '../types';
import { EscrowDetailModal } from './EscrowDetailModal';
import { EscrowFormModal } from './EscrowFormModal';
import { JurisdictionModal, SoldPortionModal, TaxEditModal, TaxYearModal } from './TaxModals';

const TH = 'px-4 py-3 font-medium text-secondary-500';
type Open =
  | { kind: 'new_escrow' }
  | { kind: 'escrow'; id: string }
  | { kind: 'tax_year' }
  | { kind: 'tax'; tax: PropertyTax }
  | { kind: 'sold' }
  | { kind: 'jurisdiction'; j?: Jurisdiction }
  | null;

/** Task 7.5 — open escrows with their two costs, upcoming taxes, reserve vs contingency. */
export function LongTailTab({ projectId, readOnly = false }: { projectId: string; readOnly?: boolean }) {
  const query = useLongTail(projectId);
  const { data: jurisdictions = [] } = useJurisdictions();
  const [open, setOpen] = useState<Open>(null);
  const [showClosed, setShowClosed] = useState(false);

  if (query.isLoading) return <Skeleton height="400px" />;
  if (query.isError || !query.data) {
    return <Alert variant="danger" title="Could not load the long-tail items">{errorMessage(query.error, 'Please try again.')}</Alert>;
  }
  const o = query.data;
  const can = { ...o.permissions };
  if (readOnly) Object.keys(can).forEach((k) => ((can as Record<string, boolean>)[k] = false));
  const noBudget = o.budget_status === 'none';
  const escrows = o.escrows.filter((e) => showClosed || !['released', 'cancelled'].includes(e.status));
  const taxes = o.taxes.filter((t) => showClosed || !['sent_to_finance', 'cancelled'].includes(t.status));

  return (
    <div className="space-y-4">
      {noBudget && <Alert variant="info" title="No budget yet">Create the budget first: escrows and tax years are budget lines.</Alert>}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <StatCard label="Open long-tail costs" value={formatMoney(o.totals.long_tail_open)}
          meta={`${o.totals.open_escrows} open escrow(s) ${formatMoney(o.totals.open_escrow_costs)} · taxes ${formatMoney(o.totals.open_taxes)}`} />
        <StatCard label="Reserve required" value={o.totals.reserve_required ? formatMoney(o.totals.reserve_required) : 'Not set'}
          accent={o.totals.below_reserve ? 'warning' : 'info'} meta="Kept in contingency. Set on the Budget tab → Contingency health → Setup." />
        <StatCard label="Contingency remaining" value={formatMoney(o.totals.contingency)} accent={o.totals.below_reserve ? 'warning' : 'success'}
          meta={o.totals.below_reserve ? 'Below the reserve: an alert is raised.' : 'Above the reserve.'} />
        <StatCard label="Cash posted in escrows" value={formatMoney(o.totals.cash_posted)}
          meta={toCents(o.totals.tax_increase) > 0 ? `Taxes billed ${formatMoney(o.totals.tax_increase)} over estimate` : 'Comes back when released'} />
      </div>

      <Card
        title="Escrows"
        subtitle="Each carries two budget lines: the bond / insurance premium and repairs to city standard."
        padding="md"
        actions={
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="ghost" onClick={() => setShowClosed((v) => !v)}>{showClosed ? 'Hide closed' : 'Show closed'}</Button>
            {can.manage_escrows && !noBudget && (
              <Button size="sm" leftIcon={<Plus className="h-4 w-4" />} onClick={() => setOpen({ kind: 'new_escrow' })}>New escrow</Button>
            )}
          </div>
        }
      >
        {escrows.length === 0 ? (
          <EmptyState title="No escrows" description="Roads to the city; landscaping, trails, common areas and benches to the HOA." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-secondary-200 bg-secondary-50">
                  <th className={TH}>Escrow</th>
                  <th className={`${TH} hidden md:table-cell`}>Posted as</th>
                  <th className={`${TH} text-right`}>Works</th>
                  <th className={`${TH} text-right`}>Premium</th>
                  <th className={`${TH} text-right`}>Repairs</th>
                  <th className={TH}>Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-secondary-100">
                {escrows.map((e) => (
                  <tr key={e.id} className="align-top hover:bg-secondary-50">
                    <td className="px-4 py-3">
                      <button type="button" className="text-left font-medium text-secondary-900 hover:text-primary-600 hover:underline"
                        onClick={() => setOpen({ kind: 'escrow', id: e.id })}>{e.name}</button>
                      <div className="text-xs text-secondary-500">{BENEFICIARY_LABELS[e.beneficiary]}: {e.covered_areas.join(', ')}</div>
                    </td>
                    <td className="hidden px-4 py-3 text-secondary-700 md:table-cell">
                      {e.security_form === 'bond' ? `Bond · ${e.holder_name ?? ''}` : 'Cash'}
                      {e.bond_expiry_date && <div className="text-xs text-secondary-500">Expires {formatDateOnly(e.bond_expiry_date)}</div>}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatMoney(e.secured_amount)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatMoney(e.premium_line_amount)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatMoney(e.repair_line_amount)}
                      {e.open_defects > 0 && <div className="text-xs text-warning-700">{e.open_defects} open defect(s)</div>}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={ESCROW_STATUS[e.status].label} variant={ESCROW_STATUS[e.status].variant} size="sm" />
                      {!e.released_date && e.expected_release_date && (
                        <div className="mt-1 text-xs text-secondary-500">Release {formatDateOnly(e.expected_release_date)}</div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card
        title="Property taxes"
        subtitle={`One budget line per tax year. ${o.upcoming_taxes.length} instalment(s) due in the next 12 months; reminders go to the manager and finance.`}
        padding="md"
        actions={
          <div className="flex flex-wrap gap-2">
            {can.manage_taxes && <Button size="sm" variant="ghost" onClick={() => setOpen({ kind: 'jurisdiction' })}>Cities &amp; counties</Button>}
            {can.manage_taxes && o.taxes.length > 0 && <Button size="sm" variant="outline" onClick={() => setOpen({ kind: 'sold' })}>Lots sold</Button>}
            {can.manage_taxes && !noBudget && (
              <Button size="sm" leftIcon={<Plus className="h-4 w-4" />} onClick={() => setOpen({ kind: 'tax_year' })}>Tax year</Button>
            )}
          </div>
        }
      >
        {taxes.length === 0 ? (
          <EmptyState title="No property taxes" description="Add a tax line for each year the land is owned." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-secondary-200 bg-secondary-50">
                  <th className={TH}>Year</th>
                  <th className={TH}>City / county</th>
                  <th className={TH}>Due</th>
                  <th className={`${TH} text-right`}>Estimate</th>
                  <th className={`${TH} text-right`}>Billed</th>
                  <th className={`${TH} text-right`}>Due now</th>
                  <th className={TH}>Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-secondary-100">
                {taxes.map((t) => (
                  <tr key={t.id} className="hover:bg-secondary-50">
                    <td className="px-4 py-3">
                      {can.manage_taxes ? (
                        <button type="button" className="font-medium text-secondary-900 hover:text-primary-600 hover:underline"
                          onClick={() => setOpen({ kind: 'tax', tax: t })}>{t.tax_year} #{t.installment_number}</button>
                      ) : `${t.tax_year} #${t.installment_number}`}
                    </td>
                    <td className="px-4 py-3 text-secondary-700">{t.jurisdiction}</td>
                    <td className="px-4 py-3 text-secondary-700">{formatDateOnly(t.due_date)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">{formatMoney(t.estimated_amount)}</td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {t.actual_amount ? formatMoney(t.actual_amount) : '—'}
                      {t.increase && toCents(t.increase) > 0 && <div className="text-xs text-danger-700">+{formatMoney(t.increase)}</div>}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatMoney(t.amount_due)}
                      {Number(t.sold_portion_percent ?? 0) > 0 && <div className="text-xs text-secondary-500">{Number(t.sold_portion_percent)}% sold</div>}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={TAX_STATUS[t.status].label} variant={TAX_STATUS[t.status].variant} size="sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {can.manage_taxes && jurisdictions.length > 0 && (
          <p className="mt-3 text-xs text-secondary-500">
            Cities &amp; counties:{' '}
            {jurisdictions.map((j, i) => (
              <span key={j.id}>
                {i > 0 && ', '}
                <button type="button" className="hover:text-primary-600 hover:underline" onClick={() => setOpen({ kind: 'jurisdiction', j })}>{j.name}</button>
              </span>
            ))}
          </p>
        )}
      </Card>

      {open?.kind === 'new_escrow' && <EscrowFormModal projectId={projectId} onClose={() => setOpen(null)} />}
      {open?.kind === 'escrow' && <EscrowDetailModal escrowId={open.id} readOnly={readOnly} onClose={() => setOpen(null)} />}
      {open?.kind === 'tax_year' && <TaxYearModal projectId={projectId} onClose={() => setOpen(null)} />}
      {open?.kind === 'tax' && <TaxEditModal tax={open.tax} onClose={() => setOpen(null)} />}
      {open?.kind === 'sold' && <SoldPortionModal projectId={projectId} onClose={() => setOpen(null)} />}
      {open?.kind === 'jurisdiction' && <JurisdictionModal jurisdiction={open.j} onClose={() => setOpen(null)} />}
    </div>
  );
}
