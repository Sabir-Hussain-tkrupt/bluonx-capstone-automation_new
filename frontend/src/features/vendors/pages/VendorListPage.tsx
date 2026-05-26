import { useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { Select } from '@/components/ui/Select';
import { Table } from '@/components/ui/Table';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { EmptyState } from '@/components/ui/EmptyState';
import { useToast } from '@/components/ui/Toast/useToast';
import { useVendors } from '@/features/vendors/hooks/useVendors';
import { useTrades } from '@/features/vendors/hooks/useTrades';
import { useCreateVendor } from '@/features/vendors/hooks/useCreateVendor';
import { VendorForm } from '@/features/vendors/components/VendorForm';
import { VendorCSVImport } from '@/features/vendors/components/VendorCSVImport';
import { InsuranceExpiringBadge } from '@/features/vendors/components/InsuranceExpiringBadge';
import type { Vendor, VendorListFilters } from '@/features/vendors/api/vendor.queries';
import type { Column } from '@/components/ui/Table/Table';
import type { StatusVariant } from '@/components/ui/types';

const statusVariantMap: Record<string, StatusVariant> = {
  active: 'success',
  inactive: 'neutral',
  suspended: 'danger',
};

const onboardingVariantMap: Record<string, StatusVariant> = {
  pending: 'warning',
  partial: 'info',
  complete: 'success',
};

export function VendorListPage() {
  const navigate = useNavigate();
  const { toast } = useToast();

  // Filter state
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [onboardingFilter, setOnboardingFilter] = useState('');
  const [tradeFilter, setTradeFilter] = useState('');
  const [sortBy, setSortBy] = useState('company_name');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  // Modal state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [showCSVImport, setShowCSVImport] = useState(false);

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

  const filters: VendorListFilters = useMemo(() => ({
    search: debouncedSearch || undefined,
    status: statusFilter || undefined,
    onboarding_status: onboardingFilter || undefined,
    trade_id: tradeFilter || undefined,
    sort_by: sortBy,
    sort_dir: sortDir,
    page,
    page_size: pageSize,
  }), [debouncedSearch, statusFilter, onboardingFilter, tradeFilter, sortBy, sortDir, page, pageSize]);

  const { data, isLoading } = useVendors(filters);
  const { data: trades = [] } = useTrades();
  const createVendorMutation = useCreateVendor();

  const vendors = data?.items ?? [];
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

  const handleRowClick = (vendor: Vendor) => {
    navigate(`/vendors/${vendor.id}`);
  };

  const columns: Column<Vendor>[] = useMemo(() => [
    {
      id: 'company_name',
      header: 'Company Name',
      accessor: 'company_name',
      sortable: true,
    },
    {
      id: 'city',
      header: 'Location',
      accessor: (row: Vendor) => [row.city, row.state].filter(Boolean).join(', ') || '\u2014',
      sortable: true,
    },
    {
      id: 'status',
      header: 'Status',
      accessor: (row: Vendor) => (
        <StatusBadge status={row.status} variant={statusVariantMap[row.status] ?? 'neutral'} />
      ),
      sortable: true,
    },
    {
      id: 'onboarding_status',
      header: 'Onboarding',
      accessor: (row: Vendor) => (
        <StatusBadge status={row.onboarding_status} variant={onboardingVariantMap[row.onboarding_status] ?? 'neutral'} />
      ),
      sortable: true,
    },
    {
      id: 'current_active_jobs',
      header: 'Active Jobs',
      accessor: (row: Vendor) => {
        const max = row.max_active_jobs;
        return max ? `${row.current_active_jobs} / ${max}` : `${row.current_active_jobs}`;
      },
      align: 'center' as const,
    },
  ], []);

  const tradeOptions = useMemo(
    () => trades.map((t) => ({ value: t.id, label: t.name })),
    [trades],
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold text-secondary-900 sm:text-2xl">Vendors</h1>
            <InsuranceExpiringBadge />
          </div>
          <p className="mt-1 text-sm text-secondary-500">
            Manage vendor companies, contacts, and trade associations.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <Button variant="outline" onClick={() => setShowCSVImport(true)}>
            Import CSV
          </Button>
          <Button onClick={() => setShowCreateForm(true)}>
            + Add Vendor
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <TextInput
          value={search}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="Search by company name..."
          size="sm"
        />
        <Select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
          placeholder="All Statuses"
          options={[
            { value: '', label: 'All Statuses' },
            { value: 'active', label: 'Active' },
            { value: 'inactive', label: 'Inactive' },
            { value: 'suspended', label: 'Suspended' },
          ]}
          size="sm"
        />
        <Select
          value={onboardingFilter}
          onChange={(e) => { setOnboardingFilter(e.target.value); setPage(1); }}
          placeholder="All Onboarding"
          options={[
            { value: '', label: 'All Onboarding' },
            { value: 'pending', label: 'Pending' },
            { value: 'partial', label: 'Partial' },
            { value: 'complete', label: 'Complete' },
          ]}
          size="sm"
        />
        <Select
          value={tradeFilter}
          onChange={(e) => { setTradeFilter(e.target.value); setPage(1); }}
          placeholder="All Trades"
          options={[{ value: '', label: 'All Trades' }, ...tradeOptions]}
          size="sm"
        />
      </div>

      {/* Table */}
      <Table
        columns={columns}
        data={vendors}
        keyExtractor={(row) => row.id}
        sortColumn={sortBy}
        sortDirection={sortDir}
        onSort={handleSort}
        onRowClick={handleRowClick}
        isLoading={isLoading}
        mobileTitle="company_name"
        pagination={{
          page,
          pageSize,
          total,
          onPageChange: setPage,
          onPageSizeChange: (size) => { setPageSize(size); setPage(1); },
        }}
        emptyState={
          <EmptyState
            title="No vendors found"
            description={
              debouncedSearch || statusFilter || onboardingFilter || tradeFilter
                ? 'Try adjusting your filters.'
                : 'Get started by adding a vendor or importing from CSV.'
            }
          />
        }
      />

      {/* Create Vendor Modal */}
      <VendorForm
        isOpen={showCreateForm}
        onClose={() => setShowCreateForm(false)}
        isLoading={createVendorMutation.isPending}
        onSubmit={(formData) => {
          createVendorMutation.mutate(formData as Parameters<typeof createVendorMutation.mutate>[0], {
            onSuccess: () => {
              setShowCreateForm(false);
              toast({ variant: 'success', message: 'Vendor created successfully.' });
            },
            onError: (error) => {
              toast({ variant: 'danger', message: (error as { message?: string }).message || 'Failed to create vendor.' });
            },
          });
        }}
      />

      {/* CSV Import Modal */}
      {showCSVImport && (
        <VendorCSVImport
          isOpen={showCSVImport}
          onClose={() => setShowCSVImport(false)}
        />
      )}
    </div>
  );
}
