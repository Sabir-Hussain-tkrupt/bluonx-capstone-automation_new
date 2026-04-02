import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { Select } from '@/components/ui/Select';
import { Table } from '@/components/ui/Table';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Modal } from '@/components/ui/Modal';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToast } from '@/components/ui/Toast/useToast';
import { ROUTES } from '@/constants/routes';
import { useBidTemplates } from '@/features/bid-templates/hooks/useBidTemplates';
import { useDeleteBidTemplate } from '@/features/bid-templates/hooks/useDeleteBidTemplate';
import { useTrades } from '@/features/vendors/hooks/useTrades';
import type { BidTemplate, BidTemplateListFilters } from '@/features/bid-templates/api/bid-template.queries';
import type { Column } from '@/components/ui/Table';

export function BidTemplateListPage() {
  const navigate = useNavigate();
  const { toast } = useToast();

  // Filter state
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [debounceTimer, setDebounceTimer] = useState<ReturnType<typeof setTimeout> | null>(null);
  const [tradeFilter, setTradeFilter] = useState('');
  const [sortBy, setSortBy] = useState('name');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  // Delete confirmation state
  const [deleteTarget, setDeleteTarget] = useState<BidTemplate | null>(null);

  // Debounced search
  const handleSearchChange = useCallback(
    (value: string) => {
      setSearch(value);
      if (debounceTimer) clearTimeout(debounceTimer);
      setDebounceTimer(
        setTimeout(() => {
          setDebouncedSearch(value);
          setPage(1);
        }, 300),
      );
    },
    [debounceTimer],
  );

  // Build filters
  const filters: BidTemplateListFilters = useMemo(
    () => ({
      search: debouncedSearch || undefined,
      trade_id: tradeFilter || undefined,
      sort_by: sortBy,
      sort_dir: sortDir,
      page,
      page_size: pageSize,
    }),
    [debouncedSearch, tradeFilter, sortBy, sortDir, page, pageSize],
  );

  const { data, isLoading } = useBidTemplates(filters);
  const templates = data?.items ?? [];
  const total = data?.total ?? 0;

  const { data: tradesData } = useTrades();
  const trades = tradesData ?? [];

  const deleteMutation = useDeleteBidTemplate();

  // Trade filter options
  const tradeOptions = useMemo(() => {
    const options = [
      { value: '', label: 'All Trades' },
      { value: 'null', label: 'General / No Trade' },
    ];
    for (const trade of trades) {
      options.push({ value: trade.id, label: trade.name });
    }
    return options;
  }, [trades]);

  // Sort handler
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

  // Delete handler
  const handleDelete = useCallback(() => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast({ variant: 'success', message: 'Template deleted successfully.' });
        setDeleteTarget(null);
      },
      onError: (error) => {
        setDeleteTarget(null);
        const apiError = error as { status?: number; message?: string };
        if (apiError.status === 409) {
          toast({
            variant: 'danger',
            message:
              'This template is in use by one or more bid packages and cannot be deleted.',
          });
        } else {
          toast({
            variant: 'danger',
            message: apiError.message || 'Failed to delete template.',
          });
        }
      },
    });
  }, [deleteTarget, deleteMutation, toast]);

  // Table columns
  const columns: Column<BidTemplate>[] = useMemo(
    () => [
      {
        id: 'name',
        header: 'Template Name',
        accessor: 'name',
        sortable: true,
      },
      {
        id: 'trade_name',
        header: 'Trade',
        accessor: (row: BidTemplate) => row.trade_name || 'General',
      },
      {
        id: 'is_lump_sum',
        header: 'Type',
        accessor: (row: BidTemplate) => (
          <StatusBadge
            status={row.is_lump_sum ? 'lump_sum' : 'line_items'}
            variant={row.is_lump_sum ? 'info' : 'success'}
            dot={false}
          />
        ),
        sortable: true,
      },
      {
        id: 'item_count',
        header: 'Items',
        accessor: (row: BidTemplate) =>
          row.is_lump_sum ? '-' : String(row.item_count),
        align: 'center' as const,
      },
      {
        id: 'created_at',
        header: 'Created',
        accessor: (row: BidTemplate) =>
          new Date(row.created_at).toLocaleDateString(),
        sortable: true,
      },
      {
        id: 'actions',
        header: '',
        accessor: (row: BidTemplate) => (
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                navigate(`/bid-templates/${row.id}/edit`);
              }}
              className="rounded p-1 text-secondary-400 hover:text-primary-600"
              aria-label="Edit template"
            >
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path d="M2.695 14.763l-1.262 3.154a.5.5 0 00.65.65l3.155-1.262a4 4 0 001.343-.885L17.5 5.5a2.121 2.121 0 00-3-3L3.58 13.42a4 4 0 00-.885 1.343z" />
              </svg>
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget(row);
              }}
              className="rounded p-1 text-secondary-400 hover:text-danger-600"
              aria-label="Delete template"
            >
              <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                <path
                  fillRule="evenodd"
                  d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.52.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z"
                  clipRule="evenodd"
                />
              </svg>
            </button>
          </div>
        ),
        width: '80px',
      },
    ],
    [navigate],
  );

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-secondary-900 sm:text-2xl">
            Bid Templates
          </h1>
          <p className="mt-1 text-sm text-secondary-500">
            Manage reusable bid templates that define how vendors submit pricing.
          </p>
        </div>
        <Button onClick={() => navigate(ROUTES.BID_TEMPLATE_NEW)}>
          + Create Template
        </Button>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <TextInput
          placeholder="Search templates..."
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
        />
        <Select
          value={tradeFilter}
          onChange={(e) => {
            setTradeFilter(e.target.value);
            setPage(1);
          }}
          options={tradeOptions}
        />
      </div>

      {/* Table */}
      <Table
        columns={columns}
        data={templates}
        keyExtractor={(row) => row.id}
        sortColumn={sortBy}
        sortDirection={sortDir}
        onSort={handleSort}
        onRowClick={(template) => navigate(`/bid-templates/${template.id}`)}
        isLoading={isLoading}
        mobileTitle="name"
        pagination={{
          page,
          pageSize,
          total,
          onPageChange: setPage,
          onPageSizeChange: (size: number) => {
            setPageSize(size);
            setPage(1);
          },
        }}
        emptyState={
          <EmptyState
            title="No bid templates found"
            description="Create a template to define how vendors submit pricing for tasks."
          />
        }
      />

      {/* Delete confirmation modal */}
      <Modal
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        title="Delete Template"
        size="sm"
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setDeleteTarget(null)}
              disabled={deleteMutation.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={handleDelete}
              isLoading={deleteMutation.isPending}
            >
              Delete
            </Button>
          </>
        }
      >
        <p className="text-sm text-secondary-600">
          Are you sure you want to delete{' '}
          <span className="font-semibold">{deleteTarget?.name}</span>? This
          action cannot be undone. All line items in this template will also be
          deleted.
        </p>
      </Modal>
    </div>
  );
}
