import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/utils/cn';
import { Skeleton } from '../Skeleton';
import { EmptyState } from '../EmptyState';

export interface Column<T> {
  id: string;
  header: string;
  accessor: keyof T | ((row: T) => React.ReactNode);
  sortable?: boolean;
  width?: string;
  align?: 'left' | 'center' | 'right';
}

export interface TablePagination {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
}

export interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (row: T) => string;
  sortColumn?: string;
  sortDirection?: 'asc' | 'desc';
  onSort?: (columnId: string) => void;
  pagination?: TablePagination;
  isLoading?: boolean;
  emptyState?: React.ReactNode;
  onRowClick?: (row: T) => void;
  className?: string;
  /** Column ID to use as the card title on mobile. Defaults to first column. */
  mobileTitle?: string;
}

const alignStyles: Record<string, string> = {
  left: 'text-left',
  center: 'text-center',
  right: 'text-right',
};

function getCellValue<T>(row: T, accessor: Column<T>['accessor']): React.ReactNode {
  if (typeof accessor === 'function') {
    return accessor(row);
  }
  const value = row[accessor];
  if (value === null || value === undefined) return '';
  return String(value);
}

function SortIcon({ direction }: { direction?: 'asc' | 'desc' }) {
  const className = 'ml-1 inline-block h-4 w-4';
  if (direction === 'asc') return <ArrowUp className={className} aria-hidden="true" />;
  if (direction === 'desc') return <ArrowDown className={className} aria-hidden="true" />;
  return <ChevronsUpDown className={className} aria-hidden="true" />;
}

/** Mobile card view for a single data row. */
function MobileCard<T>({
  row,
  columns,
  titleColumnId,
  onRowClick,
}: {
  row: T;
  columns: Column<T>[];
  titleColumnId: string;
  onRowClick?: (row: T) => void;
}) {
  const titleCol = columns.find((c) => c.id === titleColumnId) ?? columns[0];
  const detailCols = columns.filter((c) => c.id !== titleCol.id);

  const content = (
    <>
      <p className="text-sm font-semibold text-secondary-900">
        {getCellValue(row, titleCol.accessor)}
      </p>
      {detailCols.length > 0 && (
        <dl className="mt-2 space-y-1">
          {detailCols.map((col) => (
            <div key={col.id} className="flex items-baseline justify-between gap-2 text-sm">
              <dt className="shrink-0 text-secondary-500">{col.header}</dt>
              <dd className="text-right text-secondary-900">{getCellValue(row, col.accessor)}</dd>
            </div>
          ))}
        </dl>
      )}
    </>
  );

  if (onRowClick) {
    return (
      <button
        type="button"
        onClick={() => onRowClick(row)}
        className="w-full rounded-lg border border-secondary-200 bg-white p-4 text-left shadow-sm transition-colors hover:bg-secondary-50 active:bg-secondary-100"
      >
        {content}
      </button>
    );
  }

  return (
    <div className="rounded-lg border border-secondary-200 bg-white p-4 shadow-sm">
      {content}
    </div>
  );
}

/** Footer bar: result range, page-size picker, prev/next. */
function Pagination({
  pagination,
  totalPages,
  startRow,
  endRow,
}: {
  pagination: TablePagination;
  totalPages: number;
  startRow: number;
  endRow: number;
}) {
  return (
    <div className="flex flex-col gap-3 border-t border-secondary-200 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
      <p className="text-sm text-secondary-500">
        Showing <span className="font-medium">{startRow}</span> to{' '}
        <span className="font-medium">{endRow}</span> of{' '}
        <span className="font-medium">{pagination.total}</span> results
      </p>
      <div className="flex items-center gap-2">
        {pagination.onPageSizeChange && (
          <select
            value={pagination.pageSize}
            onChange={(e) => pagination.onPageSizeChange?.(Number(e.target.value))}
            className="rounded-lg border border-secondary-300 bg-white px-2 py-1 text-sm text-secondary-700 focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none"
            aria-label="Rows per page"
          >
            {[10, 25, 50, 100].map((size) => (
              <option key={size} value={size}>
                {size} / page
              </option>
            ))}
          </select>
        )}
        <nav className="flex items-center gap-1" aria-label="Pagination">
          <button
            type="button"
            disabled={pagination.page <= 1}
            onClick={() => pagination.onPageChange(pagination.page - 1)}
            className="rounded-lg px-3 py-1 text-sm font-medium text-secondary-700 hover:bg-secondary-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
            aria-label="Previous page"
          >
            Previous
          </button>
          <span className="px-2 text-sm text-secondary-500">
            {pagination.page} / {totalPages}
          </span>
          <button
            type="button"
            disabled={pagination.page >= totalPages}
            onClick={() => pagination.onPageChange(pagination.page + 1)}
            className="rounded-lg px-3 py-1 text-sm font-medium text-secondary-700 hover:bg-secondary-100 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
            aria-label="Next page"
          >
            Next
          </button>
        </nav>
      </div>
    </div>
  );
}

export function Table<T>({
  columns,
  data,
  keyExtractor,
  sortColumn,
  sortDirection,
  onSort,
  pagination,
  isLoading = false,
  emptyState,
  onRowClick,
  className,
  mobileTitle,
}: TableProps<T>) {
  const titleColumnId = mobileTitle ?? columns[0]?.id ?? '';

  // Loading state
  if (isLoading) {
    return (
      <div className={cn('overflow-hidden rounded-lg border border-secondary-200', className)}>
        {/* Mobile skeleton */}
        <div className="space-y-3 p-4 md:hidden">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="rounded-lg border border-secondary-200 bg-white p-4">
              <Skeleton width="50%" height="16px" />
              <div className="mt-3 space-y-2">
                <Skeleton height="14px" />
                <Skeleton height="14px" />
              </div>
            </div>
          ))}
        </div>
        {/* Desktop skeleton */}
        <table className="hidden w-full md:table">
          <thead>
            <tr className="border-b border-secondary-200 bg-secondary-50">
              {columns.map((col) => (
                <th key={col.id} className="px-6 py-3">
                  <Skeleton width="60%" height="16px" />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 5 }).map((_, i) => (
              <tr key={i} className="border-b border-secondary-100">
                {columns.map((col) => (
                  <td key={col.id} className="px-6 py-4">
                    <Skeleton height="16px" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  // Pagination calculations
  const totalPages = pagination
    ? Math.max(1, Math.ceil(pagination.total / pagination.pageSize))
    : 1;
  const startRow = pagination
    ? (pagination.page - 1) * pagination.pageSize + 1
    : 1;
  const endRow = pagination
    ? Math.min(pagination.page * pagination.pageSize, pagination.total)
    : data.length;

  // A page past the last one has no rows but a non-zero total. Keep the
  // pagination controls visible in that case, otherwise the only way back is
  // a reload: the empty branch below renders no Previous button.
  const isStrandedPage = data.length === 0 && !!pagination && pagination.total > 0;

  // Empty state
  if (data.length === 0) {
    return (
      <div className={cn('overflow-hidden rounded-lg border border-secondary-200', className)}>
        {/* Desktop header */}
        <table className="hidden w-full md:table">
          <thead>
            <tr className="border-b border-secondary-200 bg-secondary-50">
              {columns.map((col) => (
                <th
                  key={col.id}
                  className={cn(
                    'px-6 py-3 text-xs font-medium uppercase tracking-wider text-secondary-500',
                    alignStyles[col.align ?? 'left'],
                  )}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
        </table>
        {isStrandedPage ? (
          <EmptyState
            title="Nothing on this page"
            description={`This page is past the end of the ${pagination.total} matching results.`}
            action={
              <button
                type="button"
                onClick={() => pagination.onPageChange(1)}
                className="rounded-lg bg-primary-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-primary-700 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
              >
                Back to first page
              </button>
            }
          />
        ) : (
          emptyState ?? (
            <EmptyState
              title="No data found"
              description="There are no records to display."
            />
          )
        )}
        {isStrandedPage && (
          <Pagination
            pagination={pagination}
            totalPages={totalPages}
            startRow={0}
            endRow={0}
          />
        )}
      </div>
    );
  }

  return (
    <div className={cn('overflow-hidden rounded-lg border border-secondary-200', className)}>
      {/* Mobile card view */}
      <div className="space-y-3 p-4 md:hidden">
        {data.map((row) => (
          <MobileCard
            key={keyExtractor(row)}
            row={row}
            columns={columns}
            titleColumnId={titleColumnId}
            onRowClick={onRowClick}
          />
        ))}
      </div>

      {/* Desktop table view */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full">
          <thead>
            <tr className="border-b border-secondary-200 bg-secondary-50">
              {columns.map((col) => {
                const isSorted = sortColumn === col.id;
                const ariaSortValue = isSorted
                  ? sortDirection === 'asc'
                    ? 'ascending' as const
                    : 'descending' as const
                  : 'none' as const;

                return (
                  <th
                    key={col.id}
                    className={cn(
                      'px-6 py-3 text-xs font-medium uppercase tracking-wider text-secondary-500',
                      alignStyles[col.align ?? 'left'],
                    )}
                    style={col.width ? { width: col.width } : undefined}
                    aria-sort={col.sortable ? ariaSortValue : undefined}
                  >
                    {col.sortable && onSort ? (
                      <button
                        type="button"
                        onClick={() => onSort(col.id)}
                        className="inline-flex items-center hover:text-secondary-700 focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:outline-none"
                      >
                        {col.header}
                        <SortIcon direction={isSorted ? sortDirection : undefined} />
                      </button>
                    ) : (
                      col.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody className="divide-y divide-secondary-100 bg-white">
            {data.map((row) => (
              <tr
                key={keyExtractor(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                // A click-only row is unreachable by keyboard. The mobile card
                // view already renders a real <button>; this gives the desktop
                // row the same reachability.
                tabIndex={onRowClick ? 0 : undefined}
                onKeyDown={
                  onRowClick
                    ? (e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
                className={cn(
                  'transition-colors hover:bg-secondary-50',
                  onRowClick && 'cursor-pointer focus-visible:bg-secondary-50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary-500',
                )}
              >
                {columns.map((col) => (
                  <td
                    key={col.id}
                    className={cn(
                      'px-6 py-4 text-sm text-secondary-900',
                      alignStyles[col.align ?? 'left'],
                    )}
                  >
                    {getCellValue(row, col.accessor)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pagination && (
        <Pagination
          pagination={pagination}
          totalPages={totalPages}
          startRow={startRow}
          endRow={endRow}
        />
      )}
    </div>
  );
}
