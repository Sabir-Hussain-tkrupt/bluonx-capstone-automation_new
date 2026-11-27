import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Download, FileText, RefreshCw } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Tabs } from '@/components/ui/Tabs';
import { useToast } from '@/components/ui/Toast';
import { useTabParam } from '@/hooks/useTabParam';
import { errorMessage } from '@/lib/api';
import { useHasRole } from '@/lib/roles';
import { formatDateOnly } from '@/lib/format';
import { formatDateTime } from '@/features/contingency/components/shared';
import { formatMoney } from '@/features/budgets/utils/money';
import { PaymentDetailModal } from '../components/PaymentDetailModal';
import { DELIVERY_VARIANT, PAYMENT_STATUS, kindLabel } from '../constants';
import {
  downloadHandoffs,
  openHandoffDocument,
  useFinanceHandoffs,
  useMarkExported,
  usePayments,
  useResendHandoff,
  type PaymentScope,
} from '../hooks/usePayments';
import type { Payment } from '../types';

const TABS = [
  { id: 'queue', label: 'My approvals' },
  { id: 'pending', label: 'Pending' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'sent', label: 'Sent to finance' },
  { id: 'finance', label: 'Finance hand-off' },
];
const TAB_IDS = TABS.map((t) => t.id);
const TH = 'px-4 py-3 font-medium text-secondary-500';

/** Task 6.7 — approval queue by project, and what was sent to finance. */
export function PaymentsPage() {
  const { id: routeId } = useParams<{ id?: string }>();
  const isFinance = useHasRole('finance', 'executive');
  const [tab, setTab] = useTabParam(TAB_IDS);
  const [openId, setOpenId] = useState<string | null>(routeId ?? null);
  const tabs = TABS.filter((t) => t.id !== 'finance' || isFinance);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-secondary-900">Payments</h1>
        <p className="mt-1 text-sm text-secondary-500">
          Approve for payment on bid, variance and invoice lines. Two people above the limit, an executive above the
          executive threshold.
        </p>
      </div>
      <Tabs tabs={tabs} activeTab={tab} onChange={setTab}>
        {tab === 'finance' && isFinance ? (
          <HandoffLog onOpen={setOpenId} />
        ) : (
          <PaymentTable scope={(tab === 'finance' ? 'queue' : tab) as PaymentScope} onOpen={setOpenId} />
        )}
      </Tabs>
      {openId && <PaymentDetailModal key={openId} paymentId={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function PaymentTable({ scope, onOpen }: { scope: PaymentScope; onOpen: (id: string) => void }) {
  const query = usePayments(scope);
  const groups = useMemo(() => {
    const map = new Map<string, Payment[]>();
    for (const p of query.data ?? []) map.set(p.project_name, [...(map.get(p.project_name) ?? []), p]);
    return [...map].sort(([a], [b]) => a.localeCompare(b));
  }, [query.data]);

  if (query.isLoading) return <Skeleton height="320px" />;
  if (query.isError) {
    return (
      <Alert variant="danger" title="Could not load the payments">
        {errorMessage(query.error, 'Something went wrong. Please try again.')}
      </Alert>
    );
  }
  if (!groups.length) {
    return (
      <EmptyState
        title={scope === 'queue' ? 'Nothing waiting for you' : 'No payments'}
        description="Payments start from “Approve for payment” on a budget line, a variance or an invoice."
      />
    );
  }
  return (
    <div className="space-y-6">
      {groups.map(([project, rows]) => (
        <div key={project} className="space-y-2">
          <h3 className="text-sm font-semibold text-secondary-900">
            {project} <span className="font-normal text-secondary-500">· {rows.length}</span>
          </h3>
          <div className="overflow-x-auto rounded-lg border border-secondary-200 bg-white">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-secondary-200 bg-secondary-50">
                  <th className={TH}>Line</th>
                  <th className={`${TH} hidden md:table-cell`}>Pay to</th>
                  <th className={`${TH} text-right`}>Amount</th>
                  <th className={`${TH} hidden lg:table-cell`}>Reason</th>
                  <th className={TH}>Status</th>
                  <th className={`${TH} hidden lg:table-cell`}>Requested</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-secondary-100">
                {rows.map((p) => (
                  <tr key={p.id} className="align-top hover:bg-secondary-50">
                    <td className="px-4 py-3">
                      <button type="button" onClick={() => onOpen(p.id)} className="text-left font-medium text-secondary-900 hover:text-primary-600 hover:underline">
                        {p.line_name}
                      </button>
                      <div className="text-xs text-secondary-500">
                        {kindLabel(p)}
                        {p.trade_name && ` · ${p.trade_name}`}
                        {p.po_number && ` · PO ${p.po_number}`}
                      </div>
                    </td>
                    <td className="hidden px-4 py-3 text-secondary-700 md:table-cell">{p.vendor_name ?? '—'}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-secondary-900">
                      {formatMoney(p.amount)}
                      {Number(p.retainage_amount) > 0 && (
                        <div className="text-xs text-secondary-500">{formatMoney(p.retainage_amount)} retained</div>
                      )}
                    </td>
                    <td className="hidden max-w-xs px-4 py-3 text-secondary-700 lg:table-cell">
                      {p.status === 'rejected' ? p.rejection_reason : p.comments ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={PAYMENT_STATUS[p.status]?.label ?? p.status} variant={PAYMENT_STATUS[p.status]?.variant} size="sm" />
                      {p.routed_to_name && ['awaiting_manager'].includes(p.status) && (
                        <div className="mt-1 text-xs text-secondary-500">{p.routed_to_name}</div>
                      )}
                      {p.expected_payment_date && (
                        <div className="mt-1 text-xs text-secondary-500">Expected {formatDateOnly(p.expected_payment_date)}</div>
                      )}
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 text-secondary-700 lg:table-cell">
                      {p.requested_by_name ?? '—'}
                      <div className="text-xs text-secondary-500">{formatDateTime(p.created_at)}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

function HandoffLog({ onOpen }: { onOpen: (id: string) => void }) {
  const { toast } = useToast();
  const query = useFinanceHandoffs(true);
  const resend = useResendHandoff();
  const mark = useMarkExported();
  const [busy, setBusy] = useState<string | null>(null);
  const rows = query.data ?? [];
  const pending = rows.filter((r) => !r.exported_at);

  const download = async (format: 'csv' | 'xlsx' | 'quickbooks') => {
    setBusy(format);
    try {
      await downloadHandoffs(format, true);
    } catch (e) {
      toast({ variant: 'danger', message: errorMessage(e, 'Could not export.') });
    } finally {
      setBusy(null);
    }
  };

  if (query.isLoading) return <Skeleton height="320px" />;
  if (query.isError) {
    return <Alert variant="danger" title="Could not load the hand-offs">{errorMessage(query.error, 'Please try again.')}</Alert>;
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-secondary-600">
          {pending.length} hand-off(s) not yet exported. Exports include only those. No payment confirmation is needed back.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" leftIcon={<Download className="h-4 w-4" />} isLoading={busy === 'xlsx'} onClick={() => download('xlsx')}>Excel</Button>
          <Button size="sm" variant="outline" leftIcon={<Download className="h-4 w-4" />} isLoading={busy === 'csv'} onClick={() => download('csv')}>CSV</Button>
          <Button size="sm" variant="outline" leftIcon={<Download className="h-4 w-4" />} isLoading={busy === 'quickbooks'} onClick={() => download('quickbooks')}>QuickBooks</Button>
          <Button
            size="sm"
            disabled={!pending.length}
            isLoading={mark.isPending}
            onClick={() =>
              mark.mutate(pending.map((r) => r.id), {
                onSuccess: (r) => toast({ variant: 'success', message: `${r.updated} marked as exported.` }),
                onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not mark them.') }),
              })
            }
          >
            Mark as exported
          </Button>
        </div>
      </div>
      {!rows.length ? (
        <EmptyState title="No hand-offs yet" description="Each final approval creates a PO and emails finance." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-secondary-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-secondary-200 bg-secondary-50">
                <th className={TH}>PO</th>
                <th className={TH}>Project / line</th>
                <th className={`${TH} hidden md:table-cell`}>Trade / vendor</th>
                <th className={`${TH} text-right`}>Amount</th>
                <th className={TH}>Delivered to finance</th>
                <th className={`${TH} text-right`}> </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-secondary-100">
              {rows.map((h) => (
                <tr key={h.id} className="align-top hover:bg-secondary-50">
                  <td className="px-4 py-3">
                    <button type="button" onClick={() => onOpen(h.payment_approval_id)} className="font-medium text-secondary-900 hover:text-primary-600 hover:underline">
                      {h.po_number}
                    </button>
                    <div className="text-xs text-secondary-500">{h.payload.approved_on}</div>
                  </td>
                  <td className="px-4 py-3 text-secondary-700">
                    {h.project_name}
                    <div className="text-xs text-secondary-500">{h.payload.line}</div>
                  </td>
                  <td className="hidden px-4 py-3 text-secondary-700 md:table-cell">
                    {h.payload.trade ?? '—'}
                    <div className="text-xs text-secondary-500">{h.payload.vendor ?? '—'}</div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums">{formatMoney(h.amount)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge
                      status={h.delivery_status ?? h.status}
                      variant={DELIVERY_VARIANT[h.delivery_status ?? h.status] ?? 'neutral'}
                      size="sm"
                    />
                    <div className="mt-1 text-xs text-secondary-500">
                      {h.delivered_to ?? h.handoff_error ?? ''} {h.sent_at && `· ${formatDateTime(h.sent_at)}`}
                    </div>
                    {h.exported_at && <div className="text-xs text-secondary-500">Exported {formatDateTime(h.exported_at)}</div>}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <div className="flex justify-end gap-1">
                      {h.document_path && (
                        <Button size="sm" variant="ghost" leftIcon={<FileText className="h-4 w-4" />} onClick={() => openHandoffDocument(h.id)}>
                          PO
                        </Button>
                      )}
                      {h.status !== 'sent' && (
                        <Button
                          size="sm"
                          variant="outline"
                          leftIcon={<RefreshCw className="h-4 w-4" />}
                          isLoading={resend.isPending && resend.variables === h.id}
                          onClick={() =>
                            resend.mutate(h.id, {
                              onSuccess: () => toast({ variant: 'success', message: 'Sent to finance.' }),
                              onError: (e) => toast({ variant: 'danger', message: errorMessage(e, 'Could not send.') }),
                            })
                          }
                        >
                          Resend
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
