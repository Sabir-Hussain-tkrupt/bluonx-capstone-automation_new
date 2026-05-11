import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useBidSubmissionDetail } from '@/features/bids/hooks/useBidSubmissionDetail';
import { formatCurrency } from '@/lib/format';
import { cn } from '@/utils/cn';
import type { BidSubmissionLineItem } from '@/features/bids/types';

interface BidSubmissionDetailModalProps {
  submissionId: string | null;
  isOpen: boolean;
  onClose: () => void;
}

function formatDateTime(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatFileSize(bytes: number): string {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function TypeBadge({ type }: { type: 'lump_sum' | 'unit_price' }) {
  return (
    <span
      className={cn(
        'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
        type === 'lump_sum'
          ? 'bg-info-100 text-info-700'
          : 'bg-secondary-100 text-secondary-700',
      )}
    >
      {type === 'lump_sum' ? 'Lump Sum' : 'Unit Price'}
    </span>
  );
}

function formatQuantity(value: number | null): string {
  if (value == null) return '—';
  return Number(value).toLocaleString('en-US', {
    maximumFractionDigits: 2,
  });
}

function LineItemsTable({ items }: { items: BidSubmissionLineItem[] }) {
  if (items.length === 0) {
    return (
      <div className="rounded-md border border-secondary-200 px-4 py-8 text-center text-sm text-secondary-500">
        No line items submitted.
      </div>
    );
  }

  const grandTotal = items.reduce((sum, li) => sum + Number(li.line_total ?? 0), 0);

  return (
    <div className="overflow-hidden rounded-md border border-secondary-200">
      {/* Mobile cards */}
      <div className="space-y-3 p-3 md:hidden">
        {items.map((li, idx) => (
          <div
            key={li.id}
            className="rounded-md border border-secondary-200 bg-white p-3"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs text-secondary-500">#{idx + 1}</p>
                <p className="text-sm font-semibold text-secondary-900">{li.description}</p>
              </div>
              <TypeBadge type={li.item_type} />
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <dt className="text-secondary-500">UoM</dt>
              <dd className="text-right text-secondary-900">{li.unit_of_measure ?? '—'}</dd>
              <dt className="text-secondary-500">Qty</dt>
              <dd className="text-right text-secondary-900">
                {li.item_type === 'unit_price' ? formatQuantity(li.quantity) : '—'}
              </dd>
              <dt className="text-secondary-500">Unit Price ($)</dt>
              <dd className="text-right text-secondary-900">
                {li.item_type === 'unit_price' && li.unit_price != null
                  ? formatCurrency(li.unit_price)
                  : '—'}
              </dd>
              <dt className="text-secondary-500">Lump Sum ($)</dt>
              <dd className="text-right text-secondary-900">
                {li.item_type === 'lump_sum' && li.lump_sum_amount != null
                  ? formatCurrency(li.lump_sum_amount)
                  : '—'}
              </dd>
              <dt className="text-secondary-500">Line Total</dt>
              <dd className="text-right font-semibold text-secondary-900">
                {formatCurrency(li.line_total)}
              </dd>
            </dl>
          </div>
        ))}
        <div className="flex items-center justify-between rounded-md bg-secondary-50 px-3 py-2">
          <span className="text-sm text-secondary-700">Grand Total</span>
          <span className="text-base font-bold text-primary-600">
            {formatCurrency(grandTotal)}
          </span>
        </div>
      </div>

      {/* Desktop table */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead className="bg-secondary-50 text-xs uppercase tracking-wider text-secondary-500">
            <tr>
              <th className="px-4 py-3 text-left font-medium">#</th>
              <th className="px-4 py-3 text-left font-medium">Description</th>
              <th className="px-4 py-3 text-left font-medium">Type</th>
              <th className="px-4 py-3 text-left font-medium">UoM</th>
              <th className="px-4 py-3 text-right font-medium">Qty</th>
              <th className="px-4 py-3 text-right font-medium">Unit Price ($)</th>
              <th className="px-4 py-3 text-right font-medium">Lump Sum ($)</th>
              <th className="px-4 py-3 text-right font-medium">Line Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-secondary-100 bg-white">
            {items.map((li, idx) => (
              <tr key={li.id}>
                <td className="px-4 py-3 text-secondary-500">{idx + 1}</td>
                <td className="px-4 py-3 font-semibold text-secondary-900">
                  {li.description}
                </td>
                <td className="px-4 py-3">
                  <TypeBadge type={li.item_type} />
                </td>
                <td className="px-4 py-3 text-secondary-700">
                  {li.unit_of_measure ?? '—'}
                </td>
                <td className="px-4 py-3 text-right text-secondary-900">
                  {li.item_type === 'unit_price' ? formatQuantity(li.quantity) : '—'}
                </td>
                <td className="px-4 py-3 text-right text-secondary-900">
                  {li.item_type === 'unit_price' && li.unit_price != null
                    ? formatCurrency(li.unit_price)
                    : '—'}
                </td>
                <td className="px-4 py-3 text-right text-secondary-900">
                  {li.item_type === 'lump_sum' && li.lump_sum_amount != null
                    ? formatCurrency(li.lump_sum_amount)
                    : '—'}
                </td>
                <td className="px-4 py-3 text-right font-medium text-secondary-900">
                  {formatCurrency(li.line_total)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-secondary-50">
            <tr>
              <td
                colSpan={7}
                className="px-4 py-3 text-right text-sm text-secondary-700"
              >
                Grand Total
              </td>
              <td className="px-4 py-3 text-right text-base font-bold text-primary-600">
                {formatCurrency(grandTotal)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

export function BidSubmissionDetailModal({
  submissionId,
  isOpen,
  onClose,
}: BidSubmissionDetailModalProps) {
  const { data, isLoading, error } = useBidSubmissionDetail(submissionId);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Bid Submission" size="xl" mobileCenter>
      {isLoading ? (
        <div className="space-y-4" data-testid="bid-detail-skeleton">
          <Skeleton height="48px" />
          <Skeleton height="200px" />
          <Skeleton height="80px" />
        </div>
      ) : error || !data ? (
        <p className="text-sm text-danger-600">Failed to load bid submission.</p>
      ) : (
        <div className="space-y-6">
          {/* Header */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h3 className="truncate text-lg font-semibold text-secondary-900">
                {data.vendor_company_name ?? 'Unknown Vendor'}
              </h3>
              <p className="text-sm text-secondary-600">
                {data.vendor_contact_name ?? '—'}
                {data.vendor_contact_email && (
                  <span className="text-secondary-500"> · {data.vendor_contact_email}</span>
                )}
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <StatusBadge status={data.status} size="sm" />
                {data.is_direct_assign && (
                  <span className="inline-flex items-center rounded-full bg-info-100 px-2 py-0.5 text-xs font-medium text-info-700">
                    Direct Assign
                  </span>
                )}
                <span className="text-xs text-secondary-500">
                  Submitted {formatDateTime(data.submitted_at)}
                </span>
              </div>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-xs uppercase tracking-wide text-secondary-500">Total Bid</p>
              <p className="text-2xl font-bold text-secondary-900">
                {formatCurrency(data.total_amount)}
              </p>
            </div>
          </div>

          {/* Line Items */}
          <div>
            <h4 className="mb-3 text-sm font-semibold text-secondary-900">Line Items</h4>
            <LineItemsTable items={data.line_items} />
          </div>

          {/* Vendor Notes */}
          {data.vendor_notes && data.vendor_notes.trim() !== '' && (
            <div>
              <h4 className="mb-2 text-sm font-semibold text-secondary-900">Vendor Notes</h4>
              <div className="rounded-md border border-secondary-200 p-4">
                <p className="whitespace-pre-line text-sm text-secondary-700">
                  {data.vendor_notes}
                </p>
              </div>
            </div>
          )}

          {/* Attachments */}
          {data.attachments.length > 0 && (
            <div>
              <h4 className="mb-2 text-sm font-semibold text-secondary-900">Attachments</h4>
              <ul className="divide-y divide-secondary-100 rounded-md border border-secondary-200">
                {data.attachments.map((att) => (
                  <li
                    key={att.id}
                    className="flex items-center justify-between gap-3 px-4 py-3"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <svg
                        className="h-4 w-4 shrink-0 text-secondary-400"
                        viewBox="0 0 20 20"
                        fill="currentColor"
                        aria-hidden="true"
                      >
                        <path d="M3 3.5A1.5 1.5 0 014.5 2h6.879a1.5 1.5 0 011.06.44l3.122 3.12A1.5 1.5 0 0116 6.622V16.5a1.5 1.5 0 01-1.5 1.5h-10A1.5 1.5 0 013 16.5v-13z" />
                      </svg>
                      <span className="truncate text-sm text-secondary-700">{att.file_name}</span>
                      <span className="shrink-0 text-xs text-secondary-500">
                        {formatFileSize(att.file_size)}
                      </span>
                    </div>
                    <a
                      href={att.download_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="shrink-0 text-sm font-medium text-primary-600 hover:text-primary-700"
                    >
                      Download
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
