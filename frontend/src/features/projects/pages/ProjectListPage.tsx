import { useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { Select } from '@/components/ui/Select';
import { Table } from '@/components/ui/Table';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToast } from '@/components/ui/Toast/useToast';
import { useProjects } from '@/features/projects/hooks/useProjects';
import { useCreateProject } from '@/features/projects/hooks/useCreateProject';
import { ProjectForm } from '@/features/projects/components/ProjectForm';
import type { Project, ProjectListFilters } from '@/features/projects/api/project.queries';
import type { Column } from '@/components/ui/Table/Table';
import type { StatusVariant } from '@/components/ui/types';

const statusVariantMap: Record<string, StatusVariant> = {
  planning: 'info',
  active: 'success',
  on_hold: 'warning',
  completed: 'neutral',
  cancelled: 'danger',
};

function formatCurrency(value: number | null): string {
  if (value == null) return '\u2014';
  return Number(value).toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function formatDate(value: string | null): string {
  if (!value) return '\u2014';
  return new Date(value + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function ProjectListPage() {
  const navigate = useNavigate();
  const { toast } = useToast();

  // Filter state
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('active');
  const [sortBy, setSortBy] = useState('name');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  // Modal state
  const [showCreateForm, setShowCreateForm] = useState(false);

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

  const filters: ProjectListFilters = useMemo(() => ({
    search: debouncedSearch || undefined,
    status: statusFilter || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
    page,
    page_size: pageSize,
  }), [debouncedSearch, statusFilter, sortBy, sortDir, page, pageSize]);

  const { data, isLoading } = useProjects(filters);
  const createProjectMutation = useCreateProject();

  const projects = data?.items ?? [];
  const total = data?.total ?? 0;

  const handleSort = (columnId: string) => {
    if (sortBy === columnId) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(columnId);
      setSortDir('asc');
    }
    setPage(1);
  };

  const handleRowClick = (project: Project) => {
    navigate(`/projects/${project.id}`);
  };

  const columns: Column<Project>[] = useMemo(() => [
    {
      id: 'name',
      header: 'Project Name',
      accessor: 'name',
      sortable: true,
    },
    {
      id: 'city',
      header: 'Location',
      accessor: (row: Project) => [row.city, row.state].filter(Boolean).join(', ') || '\u2014',
      sortable: true,
    },
    {
      id: 'status',
      header: 'Status',
      accessor: (row: Project) => (
        <StatusBadge status={row.status} variant={statusVariantMap[row.status] ?? 'neutral'} />
      ),
      sortable: true,
    },
    {
      id: 'budget',
      header: 'Budget',
      accessor: (row: Project) => formatCurrency(row.budget),
      sortable: true,
      align: 'right' as const,
    },
    {
      id: 'start_date',
      header: 'Start Date',
      accessor: (row: Project) => formatDate(row.start_date),
      sortable: true,
    },
  ], []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-secondary-900 sm:text-2xl">Projects</h1>
          <p className="mt-1 text-sm text-secondary-500">
            Manage construction projects, budgets, and timelines.
          </p>
        </div>
        <div>
          <Button onClick={() => setShowCreateForm(true)}>
            + New Project
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <TextInput
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="Search by project name..."
          size="sm"
        />
        <Select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          placeholder="All Statuses"
          options={[
            { value: '', label: 'All Statuses' },
            { value: 'planning', label: 'Planning' },
            { value: 'active', label: 'Active' },
            { value: 'on_hold', label: 'On Hold' },
            { value: 'completed', label: 'Completed' },
            { value: 'cancelled', label: 'Cancelled' },
          ]}
          size="sm"
        />
      </div>

      {/* Table */}
      <Table
        columns={columns}
        data={projects}
        keyExtractor={(row) => row.id}
        sortColumn={sortBy}
        sortDirection={sortDir}
        onSort={handleSort}
        onRowClick={handleRowClick}
        isLoading={isLoading}
        mobileTitle="name"
        pagination={{
          page,
          pageSize,
          total,
          onPageChange: setPage,
          onPageSizeChange: (size) => { setPageSize(size); setPage(1); },
        }}
        emptyState={
          <EmptyState
            title="No projects found"
            description={
              debouncedSearch || statusFilter
                ? 'Try adjusting your filters.'
                : 'Get started by creating a new project.'
            }
          />
        }
      />

      {/* Create Project Modal */}
      <ProjectForm
        isOpen={showCreateForm}
        onClose={() => setShowCreateForm(false)}
        isLoading={createProjectMutation.isPending}
        onSubmit={(formData) => {
          createProjectMutation.mutate(formData as unknown as Parameters<typeof createProjectMutation.mutate>[0], {
            onSuccess: () => {
              setShowCreateForm(false);
              toast({ variant: 'success', message: 'Project created successfully.' });
            },
            onError: (error) => {
              toast({ variant: 'danger', message: (error as { message?: string }).message || 'Failed to create project.' });
            },
          });
        }}
      />
    </div>
  );
}
