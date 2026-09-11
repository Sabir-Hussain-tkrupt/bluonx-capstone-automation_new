import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { EmptyState } from '@/components/ui/EmptyState';
import { Table } from '@/components/ui/Table';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ROUTES } from '@/constants/routes';
import { useProjects } from '@/features/projects/hooks/useProjects';
import { useBidPackagesList } from '@/features/bids/hooks/useBidPackagesList';
import { useCountdown } from '@/features/bids/hooks/useCountdown';
import type {
  BidPackageListFilters,
  BidPackageListSortBy,
  BidPackageListSortOrder,
  BidPackageListStatus,
  BidPackagesListRow,
} from '@/features/bids/api/bid-packages-list.queries';
import type { Column } from '@/components/ui/Table';
import { cn } from '@/utils/cn';

type StatusChip = 'all' | BidPackageListStatus;

const STATUS_CHIPS: { value: StatusChip; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'open', label: 'Open' },
  { value: 'evaluating', label: 'Evaluating' },
  { value: 'closed', label: 'Closed' },
  { value: 'cancelled', label: 'Cancelled' },
];

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: 'deadline:asc', label: 'Deadline (soonest)' },
  { value: 'deadline:desc', label: 'Deadline (latest)' },
  { value: 'created_at:desc', label: 'Created (newest)' },
  { value: 'created_at:asc', label: 'Created (oldest)' },
  { value: 'project_name:asc', label: 'Project (A–Z)' },
  { value: 'project_name:desc', label: 'Project (Z–A)' },
];

const dateFormatter = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
});

function formatDate(value: string): string {
  return dateFormatter.format(new Date(value));
}

function bidPackageHref(row: BidPackagesListRow): string {
  return ROUTES.BID_PACKAGE_DETAIL
    .replace(':id', row.project_id)
    .replace(':taskId', row.task_id)
    .replace(':bidPackageId', row.id);
}

function DeadlineCell({ deadline }: { deadline: string }) {
  const { remaining, isPassed, passedLabel } = useCountdown(deadline);
  const label = isPassed ? (passedLabel ?? 'Deadline passed') : remaining;
  return (
    <span
      className={cn(
        'text-xs',
        isPassed ? 'font-medium text-danger-600' : 'text-secondary-700',
      )}
    >
      {label}
    </span>
  );
}

function ProgressCell({
  submitted,
  total,
}: {
  submitted: number;
  total: number;
}) {
  if (total === 0) {
    return <span className="text-secondary-400">&mdash;</span>;
  }
  const pct = Math.min(100, Math.round((submitted / total) * 100));
  return (
    <div className="space-y-1">
      <span className="text-xs text-secondary-700">
        {submitted} / {total}
      </span>
      <div
        className="h-1 w-24 overflow-hidden rounded-full bg-secondary-200"
        aria-hidden="true"
      >
        <div className="h-full bg-info-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function RoundBadge({ round }: { round: number }) {
  return (
    <span className="inline-flex items-center rounded-full bg-secondary-100 px-2 py-0.5 text-xs font-medium text-secondary-700">
      R{round}
    </span>
  );
}

export function BidPackageListPage() {
  const navigate = useNavigate();
  const [statusChip, setStatusChip] = useState<StatusChip>('all');
  const [projectId, setProjectId] = useState<string>('');
  const [sortValue, setSortValue] = useState<string>('deadline:asc');

  const [sortBy, sortOrder] = sortValue.split(':') as [
    BidPackageListSortBy,
    BidPackageListSortOrder,
  ];

  const filters: BidPackageListFilters = useMemo(
    () => ({
      status: statusChip === 'all' ? undefined : statusChip,
      project_id: projectId || undefined,
      sort_by: sortBy,
      sort_order: sortOrder,
    }),
    [statusChip, projectId, sortBy, sortOrder],
  );

  const { data: items, isLoading } = useBidPackagesList(filters);
  const { data: projectsResp } = useProjects({
    sort_by: 'name',
    sort_dir: 'asc',
    page: 1,
    page_size: 100,
  });

  const projectOptions = useMemo(
    () => [
      { value: '', label: 'All Projects' },
      ...(projectsResp?.items ?? []).map((p) => ({ value: p.id, label: p.name })),
    ],
    [projectsResp],
  );

  const hasActiveFilters = statusChip !== 'all' || !!projectId;

  const clearFilters = () => {
    setStatusChip('all');
    setProjectId('');
  };

  // Sort is driven by the Select dropdown above, not clickable headers, so the
  // shared Table's sort props are intentionally left unset (static headers).
  const columns: Column<BidPackagesListRow>[] = useMemo(
    () => [
      {
        id: 'project_task',
        header: 'Project / Task',
        // Inline spans keep the two-line stack tidy in every place this cell
        // renders: a <td>, the mobile-card title, or a <dd>.
        accessor: (row) => (
          <span className="block min-w-0">
            <span className="block truncate font-medium text-secondary-900">
              {row.project_name}
            </span>
            <span className="block truncate text-xs font-normal text-secondary-500">
              {row.task_name}
            </span>
          </span>
        ),
      },
      {
        id: 'round',
        header: 'Round',
        accessor: (row) => <RoundBadge round={row.round_number} />,
      },
      {
        id: 'deadline',
        header: 'Deadline',
        accessor: (row) => <DeadlineCell deadline={row.deadline} />,
      },
      {
        id: 'status',
        header: 'Status',
        accessor: (row) => <StatusBadge status={row.status} size="sm" minWidth />,
      },
      {
        id: 'progress',
        header: 'Progress',
        accessor: (row) => (
          <ProgressCell submitted={row.submitted_count} total={row.total_invitations} />
        ),
      },
      {
        id: 'created_at',
        header: 'Created',
        accessor: (row) => (
          <span className="text-sm text-secondary-700">{formatDate(row.created_at)}</span>
        ),
      },
    ],
    [],
  );

  const emptyState = hasActiveFilters ? (
    <EmptyState
      title="No bid packages match these filters."
      action={
        <Button variant="outline" onClick={clearFilters}>
          Clear filters
        </Button>
      }
    />
  ) : (
    <EmptyState
      title="No bid packages yet."
      description="Start bidding on a task to create one."
      action={
        <Link to={ROUTES.PROJECTS}>
          <Button>Go to Projects</Button>
        </Link>
      }
    />
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-secondary-900 sm:text-2xl">
            Bid Packages
          </h1>
          <p className="mt-1 text-sm text-secondary-500">
            All in-flight bid packages across projects.
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {STATUS_CHIPS.map((chip) => (
            <button
              key={chip.value}
              type="button"
              onClick={() => setStatusChip(chip.value)}
              className={cn(
                'rounded-full px-3 py-1 text-sm font-medium transition-colors',
                statusChip === chip.value
                  ? 'bg-primary-600 text-white'
                  : 'bg-secondary-100 text-secondary-700 hover:bg-secondary-200',
              )}
            >
              {chip.label}
            </button>
          ))}
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            options={projectOptions}
            size="sm"
            aria-label="Filter by project"
          />
          <Select
            value={sortValue}
            onChange={(e) => setSortValue(e.target.value)}
            options={SORT_OPTIONS}
            size="sm"
            aria-label="Sort"
          />
        </div>
      </div>

      {/* Body */}
      <Table
        // Darker list-card edge (see VendorListPage); scoped to list pages.
        className="border-secondary-400"
        columns={columns}
        data={items ?? []}
        keyExtractor={(row) => row.id}
        onRowClick={(row) => navigate(bidPackageHref(row))}
        isLoading={isLoading}
        mobileTitle="project_task"
        emptyState={emptyState}
      />
    </div>
  );
}
