import { useState, useMemo, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { TextInput } from '@/components/ui/TextInput';
import { Select } from '@/components/ui/Select';
import { Table } from '@/components/ui/Table';
import { EmptyState } from '@/components/ui/EmptyState';
import { useProjects } from '@/features/projects/hooks/useProjects';
import { useMilestoneOverview } from '@/features/milestones/hooks/useMilestoneOverview';
import { MilestoneStatusBadge } from '@/features/milestones/components/MilestoneStatusBadge';
import { buildMilestonePath } from '@/features/milestones/utils/buildMilestonePath';
import { formatMilestoneDate } from '@/features/milestones/utils/formatDate';
import { formatStalled } from '@/features/milestones/utils/pauseSeverity';
import type {
  MilestoneOverviewFilters,
  MilestoneOverviewRow,
} from '@/features/milestones/api/milestoneOverview.queries';
import type { Column } from '@/components/ui/Table/Table';

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'attention', label: 'Attention needed' },
  { value: 'scheduled', label: 'Scheduled' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'delayed', label: 'Delayed' },
  { value: 'unresponsive', label: 'Unresponsive' },
  { value: 'completed', label: 'Completed' },
  { value: 'cancelled', label: 'Cancelled' },
];

/** End-date cell: the working end date, the committed baseline when it has moved,
 *  and a marker when the milestone is overdue. */
function EndDateCell({ row }: { row: MilestoneOverviewRow }) {
  return (
    <div>
      <div className="flex items-center gap-1.5">
        <span>{formatMilestoneDate(row.end_date)}</span>
        {row.is_overdue && (
          <span
            className="inline-block h-1.5 w-1.5 rounded-full bg-danger-500"
            title="Overdue"
            aria-label="Overdue"
          />
        )}
      </div>
      {row.end_date_moved && (
        <p className="mt-0.5 text-xs text-secondary-400">
          committed {formatMilestoneDate(row.baseline_end_date)}
        </p>
      )}
    </div>
  );
}

export function MilestoneListPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Seed the status filter once from the URL: the dashboard "View all" link
  // passes ?status=paused. We do not sync state back to the URL (local-state
  // convention, matching VendorListPage).
  const [statusFilter, setStatusFilter] = useState(() =>
    searchParams.get('status') === 'paused' ? 'attention' : '',
  );

  const [search, setSearch] = useState('');
  const [projectFilter, setProjectFilter] = useState('');
  const [sortBy, setSortBy] = useState('days_paused');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  // Debounced search
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [debounceTimer, setDebounceTimer] = useState<ReturnType<typeof setTimeout> | null>(null);

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
    if (debounceTimer) clearTimeout(debounceTimer);
    setDebounceTimer(
      setTimeout(() => {
        setDebouncedSearch(value);
        setPage(1);
      }, 300),
    );
  }, [debounceTimer]);

  const filters: MilestoneOverviewFilters = useMemo(() => ({
    search: debouncedSearch || undefined,
    status: statusFilter || undefined,
    project_id: projectFilter || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
    page,
    page_size: pageSize,
  }), [debouncedSearch, statusFilter, projectFilter, sortBy, sortDir, page, pageSize]);

  const { data, isLoading } = useMilestoneOverview(filters);
  const { data: projectsData } = useProjects();

  const milestones = data?.items ?? [];
  const total = data?.total ?? 0;

  const projectOptions = useMemo(
    () => [
      { value: '', label: 'All Projects' },
      ...(projectsData?.items ?? []).map((p) => ({ value: p.id, label: p.name })),
    ],
    [projectsData],
  );

  const handleSort = (columnId: string) => {
    if (sortBy === columnId) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(columnId);
      setSortDir('asc');
    }
    setPage(1);
  };

  const handleRowClick = (row: MilestoneOverviewRow) => {
    navigate(buildMilestonePath(row.project_id, row.task_id, row.milestone_id));
  };

  const columns: Column<MilestoneOverviewRow>[] = useMemo(() => [
    {
      id: 'status',
      header: 'Status',
      accessor: (row) => <MilestoneStatusBadge status={row.status} size="sm" />,
      sortable: true,
    },
    {
      id: 'milestone_name',
      header: 'Milestone',
      accessor: 'milestone_name',
      sortable: true,
    },
    {
      id: 'project_name',
      header: 'Project / Task',
      accessor: (row) => (
        <div className="min-w-0">
          <p className="truncate text-sm text-secondary-900">{row.project_name}</p>
          <p className="truncate text-xs text-secondary-500">{row.task_name}</p>
        </div>
      ),
      sortable: true,
    },
    {
      id: 'vendor_company_name',
      header: 'Vendor',
      accessor: 'vendor_company_name',
      sortable: true,
    },
    {
      id: 'end_date',
      header: 'End Date',
      accessor: (row) => <EndDateCell row={row} />,
      sortable: true,
    },
    {
      id: 'days_paused',
      header: 'Stalled',
      accessor: (row) =>
        row.days_paused == null ? (
          <span className="text-secondary-400">&mdash;</span>
        ) : (
          formatStalled(row.days_paused)
        ),
      sortable: true,
      align: 'right',
    },
    {
      id: 'created_by_name',
      header: 'Created By',
      accessor: (row) => row.created_by_name ?? '—',
      sortable: true,
    },
  ], []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold text-secondary-900 sm:text-2xl">Milestones</h1>
        <p className="mt-1 text-sm text-secondary-500">
          Track milestones across every project. Stalled milestones (delayed or
          unresponsive) surface first.
        </p>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <TextInput
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="Search milestone, task, project, vendor..."
          size="sm"
        />
        <Select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          options={STATUS_OPTIONS}
          size="sm"
        />
        <Select
          value={projectFilter}
          onChange={(e) => { setProjectFilter(e.target.value); setPage(1); }}
          options={projectOptions}
          size="sm"
        />
      </div>

      {/* Table */}
      <Table
        columns={columns}
        data={milestones}
        keyExtractor={(row) => row.milestone_id}
        sortColumn={sortBy}
        sortDirection={sortDir}
        onSort={handleSort}
        onRowClick={handleRowClick}
        isLoading={isLoading}
        mobileTitle="milestone_name"
        pagination={{
          page,
          pageSize,
          total,
          onPageChange: setPage,
          onPageSizeChange: (size) => { setPageSize(size); setPage(1); },
        }}
        emptyState={
          <EmptyState
            title="No milestones found"
            description={
              debouncedSearch || statusFilter || projectFilter
                ? 'Try adjusting your filters.'
                : 'Milestones appear here once tasks are awarded and contracted.'
            }
          />
        }
      />
    </div>
  );
}
