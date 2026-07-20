import { FileText } from 'lucide-react';
import { Modal } from '@/components/ui/Modal';
import { Skeleton } from '@/components/ui/Skeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useBidSubmissionDetail } from '@/features/bids/hooks/useBidSubmissionDetail';
import { formatCurrency, formatDateOnly } from '@/lib/format';
import { BidLineItemsTable } from './BidLineItemsTable';

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
                {data.proposed_start_date && (
                  <span className="text-xs text-secondary-500">
                    · Proposed start {formatDateOnly(data.proposed_start_date)}
                  </span>
                )}
              </div>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-xs uppercase tracking-wide text-secondary-500">Total Bid</p>
              <p className="text-2xl font-bold text-secondary-900">
                {formatCurrency(data.total_amount)}
              </p>
              {data.proposed_start_date && (
                <p className="mt-1 text-xs text-secondary-500">
                  Start: {formatDateOnly(data.proposed_start_date)}
                </p>
              )}
            </div>
          </div>

          {/* Line Items */}
          <div>
            <h4 className="mb-3 text-sm font-semibold text-secondary-900">Line Items</h4>
            <BidLineItemsTable items={data.line_items} />
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
                      <FileText className="h-4 w-4 shrink-0 text-secondary-400" aria-hidden="true" />
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
