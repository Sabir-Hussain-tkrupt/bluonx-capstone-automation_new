import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Pencil, Trash2 } from 'lucide-react';
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
        // Backend's 409 now names the referencing package(s); surface it verbatim.
        toast({
          variant: 'danger',
          message: apiError.message || 'Failed to delete template.',
        });
      },
    });
  }, [deleteTarget, deleteMutation, toast]);

  // Table columns
  const columns: Column<BidTemplate>[] = useMemo(
    () => [
      {
        id: 'name',
        header: 'Template Name',
        accessor: (row: BidTemplate) => (
          <div className="flex items-center gap-2">
            <span>{row.name}</span>
            {row.is_in_use && (
              <span
                className="rounded-full bg-info-50 px-2 py-0.5 text-xs font-medium text-info-700"
                title="Locked: in use by a live bid package"
              >
                In use
              </span>
            )}
          </div>
        ),
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
              <Pencil className="h-4 w-4" aria-hidden="true" />
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
              <Trash2 className="h-4 w-4" aria-hidden="true" />
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
