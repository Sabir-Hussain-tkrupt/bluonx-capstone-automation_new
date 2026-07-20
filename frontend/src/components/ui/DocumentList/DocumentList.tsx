import { Download, FileText, Loader2, Trash2 } from 'lucide-react';
import { cn } from '@/utils/cn';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { EmptyState } from '@/components/ui/EmptyState';
import type { StatusVariant } from '@/components/ui/types';

export interface DocumentItem {
  id: string;
  file_name: string;
  file_size?: number | null;
  file_type?: string | null;
  uploaded_at: string;
  /** Vendor-specific fields (optional) */
  document_type?: string;
  expiration_date?: string | null;
  status?: string;
}

export interface DocumentListProps {
  documents: DocumentItem[];
  onDownload: (docId: string) => void;
  onDelete?: (docId: string) => void;
  /** ID of document currently being deleted */
  isDeleting?: string | null;
  /** ID of document currently being downloaded */
  isDownloading?: string | null;
  emptyMessage?: string;
}

const docTypeLabels: Record<string, string> = {
  w9: 'W-9',
  insurance_certificate: 'Insurance Certificate',
  master_trade_agreement: 'Master Trade Agreement',
};

const statusVariantMap: Record<string, StatusVariant> = {
  valid: 'success',
  expired: 'danger',
  pending_review: 'warning',
};

function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function isExpiringSoon(expirationDate: string): boolean {
  const expiry = new Date(expirationDate + 'T00:00:00');
  const now = new Date();
  const daysUntilExpiry = (expiry.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  return daysUntilExpiry > 0 && daysUntilExpiry <= 30;
}

export function DocumentList({
  documents,
  onDownload,
  onDelete,
  isDeleting,
  isDownloading,
  emptyMessage = 'No documents uploaded yet.',
}: DocumentListProps) {
  if (documents.length === 0) {
    return <EmptyState title="No documents" description={emptyMessage} />;
  }

  return (
    <div className="space-y-2">
      {documents.map((doc) => {
        const expiring = doc.expiration_date && doc.status !== 'expired' && isExpiringSoon(doc.expiration_date);

        return (
          <div
            key={doc.id}
            className="flex flex-col gap-3 rounded-lg border border-secondary-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between"
          >
            {/* Left: file info */}
            <div className="flex min-w-0 items-start gap-3">
              <FileText className="mt-0.5 h-5 w-5 shrink-0 text-secondary-400" aria-hidden="true" />
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-secondary-900">{doc.file_name}</p>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-secondary-500">
                  {doc.document_type && (
                    <span className="font-medium text-secondary-700">
                      {docTypeLabels[doc.document_type] ?? doc.document_type}
                    </span>
                  )}
                  {doc.file_size != null && <span>{formatFileSize(doc.file_size)}</span>}
                  <span>{formatDate(doc.uploaded_at)}</span>
                  {doc.expiration_date && (
                    <span className={cn(expiring && 'font-medium text-warning-600')}>
                      Expires: {formatDate(doc.expiration_date)}
                      {expiring && ' (soon)'}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Right: status + actions */}
            <div className="flex shrink-0 items-center gap-2">
              {doc.status && (
                <StatusBadge
                  status={doc.status}
                  variant={statusVariantMap[doc.status] ?? 'neutral'}
                />
              )}

              <button
                type="button"
                onClick={() => onDownload(doc.id)}
                disabled={isDownloading === doc.id}
                className="rounded p-1.5 text-secondary-500 hover:bg-secondary-100 hover:text-primary-600 disabled:opacity-50"
                aria-label={`Download ${doc.file_name}`}
                title="Download"
              >
                {isDownloading === doc.id ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Download className="h-4 w-4" aria-hidden="true" />
                )}
              </button>

              {onDelete && (
                <button
                  type="button"
                  onClick={() => onDelete(doc.id)}
                  disabled={isDeleting === doc.id}
                  className="rounded p-1.5 text-secondary-500 hover:bg-danger-50 hover:text-danger-600 disabled:opacity-50"
                  aria-label={`Delete ${doc.file_name}`}
                  title="Delete"
                >
                  {isDeleting === doc.id ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  )}
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
