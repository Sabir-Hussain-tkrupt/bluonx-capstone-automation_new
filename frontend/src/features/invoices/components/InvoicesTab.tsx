import { useMemo, useState } from 'react';
import { Download, MoreHorizontal, Send, XCircle } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { DropdownMenu, DropdownMenuItem } from '@/components/ui/DropdownMenu';
import { IconButton } from '@/components/ui/IconButton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Table, type Column } from '@/components/ui/Table';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToast } from '@/components/ui/Toast';
import { errorMessage } from '@/lib/api';
import { formatDateOnly } from '@/lib/format';
import { useHasRole } from '@/lib/roles';
import { useBudgetLines, useBudgetSummary } from '@/features/budgets/hooks/useBudget';
import { formatMoney } from '@/features/budgets/utils/money';
import type { Invoice } from '../api/invoice.api';
import { useCancelInvoice, useInvoiceDownload, useInvoices } from '../hooks/useInvoices';
import { CategoriseInvoiceModal } from './CategoriseInvoiceModal';
import { InvoiceUploadModal } from './InvoiceUploadModal';

interface InvoicesTabProps {
  projectId: string;
  readOnly?: boolean;
}

const STATUS_VARIANT: Record<string, 'neutral' | 'info' | 'warning' | 'success' | 'danger'> = {
  received: 'neutral',
  categorised: 'info',
  in_approval: 'warning',
  approved: 'success',
  rejected: 'danger',
  cancelled: 'neutral',
};

/**
 * Task 2.6 — internal invoices (e.g. the attorney) for T&M lines. Field
 * managers, PMs and finance upload; finance / executives / admins see every
 * invoice, other uploaders their own (the server decides).
 */
export function InvoicesTab({ projectId, readOnly = false }: InvoicesTabProps) {
  const { toast } = useToast();
  const canUse = useHasRole('field_manager', 'finance', 'project_manager');
  const seesAll = useHasRole('finance', 'executive');
  const invoicesQuery = useInvoices(projectId, canUse);
  const { data: summary } = useBudgetSummary(projectId);
  const { data: lines = [] } = useBudgetLines(projectId);
  const cancel = useCancelInvoice(projectId);
  const { download, downloadingId } = useInvoiceDownload();

  const [showUpload, setShowUpload] = useState(false);
  const [categoriseTarget, setCategoriseTarget] = useState<Invoice | null>(null);
  const [cancelTarget, setCancelTarget] = useState<Invoice | null>(null);

  const hasBudget = !!summary && summary.budget_status !== 'none';

  const columns: Column<Invoice>[] = useMemo(
    () => [
      {
        id: 'payee',
        header: 'Payee',
        accessor: (row) => (
          <div>
            <div className="font-medium text-secondary-900">{row.payee_name ?? row.vendor_name ?? '—'}</div>
            {row.invoice_number && <div className="text-xs text-secondary-500">{row.invoice_number}</div>}
          </div>
        ),
      },
      { id: 'date', header: 'Invoice date', accessor: (row) => formatDateOnly(row.invoice_date) },
      {
        id: 'amount',
        header: 'Amount',
        align: 'right',
        accessor: (row) => <span className="tabular-nums">{formatMoney(row.amount)}</span>,
      },
      { id: 'line', header: 'Budget line', accessor: (row) => row.budget_line_name ?? '—' },
      {
        id: 'status',
        header: 'Status',
        accessor: (row) => <StatusBadge status={row.status} variant={STATUS_VARIANT[row.status]} minWidth />,
      },
      { id: 'uploaded_by', header: 'Uploaded by', accessor: (row) => row.uploaded_by_name ?? '—' },
      {
        id: 'actions',
        header: '',
        align: 'right',
        accessor: (row) => (
          <DropdownMenu
            trigger={<IconButton icon={<MoreHorizontal className="h-4 w-4" />} aria-label={`Actions for invoice ${row.invoice_number ?? row.file_name}`} />}
          >
            <DropdownMenuItem
              icon={<Download className="h-4 w-4" />}
              disabled={downloadingId === row.id}
              onClick={() => download(row.id)}
            >
              Download
            </DropdownMenuItem>
            {!readOnly && (row.status === 'received' || row.status === 'categorised') && (
              <>
                <DropdownMenuItem
                  icon={<Send className="h-4 w-4" />}
                  disabled={!hasBudget}
                  onClick={() => setCategoriseTarget(row)}
                >
                  Categorise &amp; send for approval
                </DropdownMenuItem>
                <DropdownMenuItem icon={<XCircle className="h-4 w-4" />} destructive onClick={() => setCancelTarget(row)}>
                  Cancel invoice
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenu>
        ),
      },
    ],
    [download, downloadingId, readOnly, hasBudget],
  );

  if (!canUse) {
    return (
      <EmptyState
        title="Invoices are not available for your role"
        description="Field managers, project managers and finance can upload and categorise internal invoices."
      />
    );
  }

  if (invoicesQuery.isError) {
    return (
      <Alert variant="danger" title="Could not load invoices">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <span>{errorMessage(invoicesQuery.error, 'Something went wrong. Please try again.')}</span>
          <Button variant="outline" size="sm" onClick={() => invoicesQuery.refetch()}>Retry</Button>
        </div>
      </Alert>
    );
  }

  const handleCancel = () => {
    if (!cancelTarget) return;
    cancel.mutate(cancelTarget.id, {
      onSuccess: () => {
        toast({ variant: 'success', message: 'Invoice cancelled.' });
        setCancelTarget(null);
      },
      onError: (e) => {
        toast({ variant: 'danger', message: errorMessage(e, 'Could not cancel the invoice.') });
        setCancelTarget(null);
      },
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-secondary-500">
          {seesAll ? 'All internal invoices on this project.' : 'Invoices you uploaded on this project.'}
          {!hasBudget && ' Categorising needs a project budget.'}
        </p>
        {!readOnly && <Button onClick={() => setShowUpload(true)}>+ Upload Invoice</Button>}
      </div>

      <Table
        className="border-secondary-400"
        columns={columns}
        data={invoicesQuery.data ?? []}
        keyExtractor={(row) => row.id}
        isLoading={invoicesQuery.isLoading}
        mobileTitle="payee"
        emptyState={
          <EmptyState
            title="No invoices yet"
            description="Upload invoices for internal T&M work (e.g. the attorney), then categorise each one to a budget line."
          />
        }
      />

      <InvoiceUploadModal projectId={projectId} isOpen={showUpload} onClose={() => setShowUpload(false)} />

      <CategoriseInvoiceModal
        projectId={projectId}
        invoice={categoriseTarget}
        lines={lines}
        budgetStatus={summary?.budget_status ?? 'none'}
        onClose={() => setCategoriseTarget(null)}
      />

      <ConfirmDialog
        isOpen={!!cancelTarget}
        title="Cancel invoice"
        message={<>Cancel invoice <strong>{cancelTarget?.invoice_number ?? cancelTarget?.file_name}</strong>? It stays on record as cancelled.</>}
        confirmText="Cancel invoice"
        isLoading={cancel.isPending}
        onConfirm={handleCancel}
        onCancel={() => setCancelTarget(null)}
      />
    </div>
  );
}
