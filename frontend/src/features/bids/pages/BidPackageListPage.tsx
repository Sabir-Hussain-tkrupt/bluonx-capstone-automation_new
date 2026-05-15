import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { EmptyState } from '@/components/ui/EmptyState';
import { ROUTES } from '@/constants/routes';
import { useProjects } from '@/features/projects/hooks/useProjects';
import { useBidPackagesList } from '@/features/bids/hooks/useBidPackagesList';
import {
  BidPackagesListTable,
  BidPackagesListSkeleton,
} from '@/features/bids/components/BidPackagesListTable';
import type {
  BidPackageListFilters,
  BidPackageListSortBy,
  BidPackageListSortOrder,
  BidPackageListStatus,
} from '@/features/bids/api/bid-packages-list.queries';
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

export function BidPackageListPage() {
  const [statusChip, setStatusChip] = useState<StatusChip>('open');
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
      {isLoading ? (
        <BidPackagesListSkeleton />
      ) : !items || items.length === 0 ? (
        hasActiveFilters ? (
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
        )
      ) : (
        <BidPackagesListTable items={items} />
      )}
    </div>
  );
}
