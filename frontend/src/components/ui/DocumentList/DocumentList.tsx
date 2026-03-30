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

function FileIcon({ className }: { className?: string }) {
  return (
    <svg className={cn('h-5 w-5', className)} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M3 3.5A1.5 1.5 0 014.5 2h6.879a1.5 1.5 0 011.06.44l3.122 3.12A1.5 1.5 0 0116 6.622V16.5a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 012 16.5v-13z" />
    </svg>
  );
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
              <FileIcon className="mt-0.5 shrink-0 text-secondary-400" />
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
                  <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                    <path d="M10.75 2.75a.75.75 0 00-1.5 0v8.614L6.295 8.235a.75.75 0 10-1.09 1.03l4.25 4.5a.75.75 0 001.09 0l4.25-4.5a.75.75 0 00-1.09-1.03l-2.955 3.129V2.75z" />
                    <path d="M3.5 12.75a.75.75 0 00-1.5 0v2.5A2.75 2.75 0 004.75 18h10.5A2.75 2.75 0 0018 15.25v-2.5a.75.75 0 00-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5z" />
                  </svg>
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
                    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                  ) : (
                    <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                      <path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 01.79.713l.5 7a.75.75 0 01-1.498.107l-.5-7a.75.75 0 01.707-.79zm3.633.713a.75.75 0 10-1.498-.107l-.5 7a.75.75 0 101.498.107l.5-7z" clipRule="evenodd" />
                    </svg>
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
