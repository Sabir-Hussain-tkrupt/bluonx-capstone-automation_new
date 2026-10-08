import { useState, useMemo, useCallback } from 'react';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { Select } from '@/components/ui/Select';
import { Table } from '@/components/ui/Table';
import type { Column } from '@/components/ui/Table';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/Toast/useToast';
import { errorMessage } from '@/lib/api';
import { useTrades } from '@/features/vendors/hooks/useTrades';
import {
  useTaskTemplates,
  useCreateTaskTemplate,
  useUpdateTaskTemplate,
  useDeleteTaskTemplate,
} from '../hooks/useTaskTemplates';
import { TaskTemplateModal } from '../components/TaskTemplateModal';
import type { TaskTemplate, TaskTemplateFormData } from '../types/taskTemplate.types';

export function TaskTemplateListPage() {
  const { toast } = useToast();
  const [search, setSearch] = useState('');
  const [phaseFilter, setPhaseFilter] = useState<'all' | 'due_diligence' | 'development'>('all');
  const [tradeFilter, setTradeFilter] = useState<string>('');
  const [sortBy, setSortBy] = useState('name');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<TaskTemplate | null>(null);
  const [deleteCandidate, setDeleteCandidate] = useState<TaskTemplate | null>(null);

  const { data: trades = [] } = useTrades();

  const tradeOptions = useMemo(() => [
    { value: '', label: 'All Trades' },
    ...trades.map((t) => ({ value: t.id, label: t.name })),
  ], [trades]);

  const handleSort = useCallback(
    (columnId: string) => {
      if (columnId === sortBy) {
        setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortBy(columnId);
        setSortDir('asc');
      }
      setPage(1);
    },
    [sortBy],
  );

  const filters = useMemo(
    () => ({
      search: search.trim() || undefined,
      phase: phaseFilter !== 'all' ? phaseFilter : undefined,
      trade_id: tradeFilter || undefined,
      sort_by: sortBy,
      sort_dir: sortDir,
      page,
      page_size: pageSize,
    }),
    [search, phaseFilter, tradeFilter, sortBy, sortDir, page, pageSize],
  );

  const { data, isLoading } = useTaskTemplates(filters);
  const createMutation = useCreateTaskTemplate();
  const updateMutation = useUpdateTaskTemplate();
  const deleteMutation = useDeleteTaskTemplate();

  const handleCreate = () => {
    setSelectedTemplate(null);
    setIsModalOpen(true);
  };

  const handleEdit = (template: TaskTemplate) => {
    setSelectedTemplate(template);
    setIsModalOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteCandidate) return;
    try {
      await deleteMutation.mutateAsync(deleteCandidate.id);
      toast({ variant: 'success', message: 'Task template deleted successfully.' });
      setDeleteCandidate(null);
    } catch (err) {
      toast({ variant: 'danger', message: errorMessage(err, 'Failed to delete task template.') });
    }
  };

  const handleModalSubmit = async (formData: TaskTemplateFormData) => {
    try {
      if (selectedTemplate) {
        await updateMutation.mutateAsync({
          id: selectedTemplate.id,
          payload: formData,
        });
        toast({ variant: 'success', message: 'Task template updated successfully.' });
      } else {
        await createMutation.mutateAsync(formData);
        toast({ variant: 'success', message: 'Task template created successfully.' });
      }
      setIsModalOpen(false);
      setSelectedTemplate(null);
    } catch (err) {
      toast({ variant: 'danger', message: errorMessage(err, 'Failed to save task template.') });
    }
  };

  const templates = data?.items || [];
  const total = data?.total || 0;

  const columns: Column<TaskTemplate>[] = useMemo(
    () => [
      {
        id: 'name',
        header: 'Template Name',
        accessor: (row) => (
          <span className="font-normal text-secondary-900">{row.name}</span>
        ),
        sortable: true,
      },
      {
        id: 'description',
        header: 'Description',
        accessor: (row) => (
          <span className="text-sm font-normal text-secondary-600">
            {row.description || '—'}
          </span>
        ),
      },
      {
        id: 'trade_name',
        header: 'Trade',
        accessor: (row) => (
          <span className="text-sm font-normal text-secondary-700">{row.trade_name || 'General'}</span>
        ),
      },
      {
        id: 'phase',
        header: 'Phase',
        accessor: (row) => (
          <span className="text-sm font-normal text-secondary-700">
            {row.phase === 'due_diligence' ? 'Due Diligence' : 'Development'}
          </span>
        ),
      },
      {
        id: 'bid_type',
        header: 'Bid Type',
        accessor: (row) => (
          <span className="text-sm font-normal text-secondary-700 capitalize">
            {row.bid_type === 'competitive'
              ? 'Competitive'
              : row.bid_type === 'direct_assign'
              ? 'Direct Assign'
              : 'Internal'}
          </span>
        ),
      },
      {
        id: 'is_active',
        header: 'Status',
        accessor: (row) => (
          <StatusBadge
            status={row.is_active ? 'active' : 'inactive'}
            minWidth
          />
        ),
      },
      {
        id: 'budget_estimate',
        header: 'Budget',
        accessor: (row) =>
          `$${(row.budget_estimate || 0).toLocaleString('en-US', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2,
          })}`,
        align: 'right',
      },
      {
        id: 'actions',
        header: 'Actions',
        accessor: (row) => (
          <div className="flex items-center justify-end gap-1">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleEdit(row);
              }}
              className="rounded p-1 text-secondary-400 hover:text-primary-600"
              aria-label="Edit template"
              title="Edit template"
            >
              <Pencil className="h-4 w-4" aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteCandidate(row);
              }}
              className="rounded p-1 text-secondary-400 hover:text-danger-600"
              aria-label="Delete template"
              title="Delete template"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        ),
        width: '90px',
        align: 'right',
      },
    ],
    [],
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-secondary-900 sm:text-2xl">
            Task Templates
          </h1>
          <p className="mt-1 text-sm text-secondary-500">
            Manage reusable task templates used for seeding project scopes and default tasks.
          </p>
        </div>
        <Button onClick={handleCreate} className="inline-flex items-center gap-2">
          <Plus className="h-4 w-4" />
          Create Template
        </Button>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between rounded-lg border border-secondary-200 bg-white p-4 shadow-sm">
        <div className="flex flex-1 items-center gap-3">
          <div className="w-full max-w-xs">
            <TextInput
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search templates..."
            />
          </div>

          <div className="w-48">
            <Select
              value={tradeFilter}
              onChange={(e) => {
                setTradeFilter(e.target.value);
                setPage(1);
              }}
              options={tradeOptions}
            />
          </div>
        </div>

        {/* Phase Filter Tabs */}
        <div className="flex rounded-lg border border-secondary-200 p-1 bg-secondary-50">
          <button
            onClick={() => {
              setPhaseFilter('all');
              setPage(1);
            }}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              phaseFilter === 'all'
                ? 'bg-white text-secondary-900 shadow-sm'
                : 'text-secondary-600 hover:text-secondary-900'
            }`}
          >
            All
          </button>
          <button
            onClick={() => {
              setPhaseFilter('due_diligence');
              setPage(1);
            }}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              phaseFilter === 'due_diligence'
                ? 'bg-white text-secondary-900 shadow-sm'
                : 'text-secondary-600 hover:text-secondary-900'
            }`}
          >
            Due Diligence
          </button>
          <button
            onClick={() => {
              setPhaseFilter('development');
              setPage(1);
            }}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              phaseFilter === 'development'
                ? 'bg-white text-secondary-900 shadow-sm'
                : 'text-secondary-600 hover:text-secondary-900'
            }`}
          >
            Development
          </button>
        </div>
      </div>

      {/* Table */}
      <Table
        className="border-secondary-400"
        columns={columns}
        data={templates}
        keyExtractor={(row) => row.id}
        sortColumn={sortBy}
        sortDirection={sortDir}
        onSort={handleSort}
        isLoading={isLoading}
        mobileTitle="name"
        pagination={{
          page,
          pageSize,
          total,
          onPageChange: setPage,
          onPageSizeChange: (size) => {
            setPageSize(size);
            setPage(1);
          },
        }}
      />

      {/* Create / Edit Modal */}
      <TaskTemplateModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleModalSubmit}
        initialData={selectedTemplate}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={!!deleteCandidate}
        title="Delete Task Template"
        message={
          <>
            Are you sure you want to delete{' '}
            <span className="font-semibold">{deleteCandidate?.name}</span>? This will soft-delete
            the task template. Existing tasks created from this template will not be affected.
          </>
        }
        confirmText="Delete Template"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteCandidate(null)}
      />
    </div>
  );
}
