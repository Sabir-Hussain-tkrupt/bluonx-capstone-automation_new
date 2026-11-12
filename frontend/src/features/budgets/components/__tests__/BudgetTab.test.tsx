import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { BudgetTab } from '../BudgetTab';
import type { BudgetLine, BudgetSummary } from '../../types';

const userEvent = userEventBase.setup({ delay: null });
const P = 'p-1';

const isAdminMock = vi.fn();
const summaryMock = vi.fn();
const linesMock = vi.fn();
const createMutate = vi.fn();
const baselineMutate = vi.fn();

vi.mock('@/lib/roles', () => ({ useHasRole: () => isAdminMock() }));

vi.mock('../../hooks/useBudget', () => ({
  useBudgetSummary: () => summaryMock(),
  useBudgetLines: () => linesMock(),
  useCreateBudget: () => ({ mutate: createMutate, isPending: false }),
  useBaselineBudget: () => ({ mutate: baselineMutate, isPending: false }),
  useSyncAwards: () => ({ mutate: vi.fn(), isPending: false }),
  useRemoveBudgetLine: () => ({ mutate: vi.fn(), isPending: false }),
  useReorderBudgetLines: () => ({ mutate: vi.fn(), isPending: false }),
  useAddBudgetLine: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateBudgetLine: () => ({ mutate: vi.fn(), isPending: false }),
  useLandClosings: () => ({ data: [], isLoading: false }),
  useAddLandClosing: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateLandClosing: () => ({ mutate: vi.fn(), isPending: false }),
  usePreviewBudgetImport: () => ({ mutate: vi.fn(), isPending: false }),
  useApplyBudgetImport: () => ({ mutate: vi.fn(), isPending: false }),
}));

function summary(over: Partial<BudgetSummary> = {}): BudgetSummary {
  return {
    project_id: P, project_name: 'Demo', budget_status: 'draft', approved_budget_total: null,
    contingency_percent: 15, budget_baselined_at: null, total_budget: 100000, committed: 0, spent: 0,
    remaining: 100000, pending_approval: 0, contingency_now: 10000, contingency_at_baseline: null,
    land_total: 0, contingency_base: 90000, line_count: 3, lines_missing_dates: 0, tasks_without_line: 0,
    flat_ok: true, ...over,
  };
}

function line(over: Partial<BudgetLine>): BudgetLine {
  return {
    id: 'l', project_id: P, task_id: null, template_line_id: null, parent_line_id: null, line_type: 'permit',
    line_subtype: null, name: 'Line', description: null, section_name: 'Soft costs', sort_order: 1,
    original_estimate: null, budget_amount: 0, committed_amount: 0, award_id: null, contract_id: null,
    is_locked: false, locked_at: null, lock_reason: null, anticipated_start_date: '2027-01-01',
    anticipated_end_date: '2027-01-31', payment_terms_days: 30, cash_bucket: 'land', approval_state: 'not_requested',
    is_payment_exempt: false, task_name: null, task_status: null, task_bid_type: null, trade_name: null,
    award_status: null, award_amount: null, vendor_id: null, vendor_name: null, contract_number: null,
    contract_status: null, variance_id: null, variance_status: null, variance_total: 0, variance_count: 0,
    invoiced: 0, committed: 0, spent: 0, pending_approval: 0, remaining: 0, bid_vs_estimate: null,
    has_dates: true, closings_total: 0, closings_count: 0, ...over,
  };
}

const LINES = [
  line({ id: 'a', name: 'Permits', budget_amount: 0.1, remaining: 0.1, sort_order: 1 }),
  line({ id: 'b', name: 'Impact fee', line_type: 'impact_fee', budget_amount: 0.2, remaining: 0.2, sort_order: 2 }),
  line({ id: 'c', name: 'Clearing', line_type: 'bid_activity', task_id: 't1', section_name: 'Site work',
         budget_amount: 22000, committed: 22000, vendor_name: 'Demo Earthworks', is_locked: true, sort_order: 3,
         has_dates: false, anticipated_start_date: null, anticipated_end_date: null }),
];

describe('BudgetTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    linesMock.mockReturnValue({ data: LINES, isLoading: false, isError: false });
  });

  it('offers admins to create a budget when none exists', async () => {
    isAdminMock.mockReturnValue(true);
    summaryMock.mockReturnValue({ data: summary({ budget_status: 'none' }), isLoading: false, isError: false });
    linesMock.mockReturnValue({ data: [], isLoading: false, isError: false });
    renderWithRouter(<BudgetTab projectId={P} />);

    await userEvent.click(screen.getByRole('button', { name: /create budget/i }));
    await userEvent.type(screen.getByLabelText(/contingency %/i), '12.5');
    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /create budget/i }));
    expect(createMutate).toHaveBeenCalledWith({ contingency_percent: '12.5' }, expect.anything());
  });

  it('non-admins see no create button', () => {
    isAdminMock.mockReturnValue(false);
    summaryMock.mockReturnValue({ data: summary({ budget_status: 'none' }), isLoading: false, isError: false });
    linesMock.mockReturnValue({ data: [], isLoading: false, isError: false });
    renderWithRouter(<BudgetTab projectId={P} />);
    expect(screen.getByText(/has not created a budget/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /create budget/i })).not.toBeInTheDocument();
  });

  it('draft: admin can baseline after confirming', async () => {
    isAdminMock.mockReturnValue(true);
    summaryMock.mockReturnValue({ data: summary(), isLoading: false, isError: false });
    renderWithRouter(<BudgetTab projectId={P} />);
    await userEvent.click(screen.getByRole('button', { name: /baseline budget/i }));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /baseline budget/i }));
    expect(baselineMutate).toHaveBeenCalled();
  });

  it('groups lines by heading with cent-exact subtotals and a total', () => {
    isAdminMock.mockReturnValue(true);
    summaryMock.mockReturnValue({ data: summary(), isLoading: false, isError: false });
    renderWithRouter(<BudgetTab projectId={P} />);
    expect(screen.getByText('Soft costs subtotal')).toBeInTheDocument();
    // 0.1 + 0.2 must render as $0.30, not $0.30000000000000004 or $0.31
    const softRow = screen.getByText('Soft costs subtotal').closest('tr')!;
    expect(within(softRow).getByText('$0.30')).toBeInTheDocument();
    const totalRow = screen.getByText('Total').closest('tr')!;
    expect(within(totalRow).getAllByText('$22,000.30').length).toBeGreaterThan(0);
    expect(screen.getByLabelText(/locked: contract executed/i)).toBeInTheDocument();
    expect(screen.getByText('Dates missing')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Clearing' })).toHaveAttribute('href', `/projects/${P}/tasks/t1`);
  });

  it('read-only for non-admins: no add / edit controls', () => {
    isAdminMock.mockReturnValue(false);
    summaryMock.mockReturnValue({ data: summary({ budget_status: 'baselined', approved_budget_total: 100000 }), isLoading: false, isError: false });
    renderWithRouter(<BudgetTab projectId={P} />);
    expect(screen.queryByRole('button', { name: /add line/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /actions for/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /export/i })).toBeInTheDocument();
  });

  it('archived projects are read-only even for admins', () => {
    isAdminMock.mockReturnValue(true);
    summaryMock.mockReturnValue({ data: summary(), isLoading: false, isError: false });
    renderWithRouter(<BudgetTab projectId={P} readOnly />);
    expect(screen.queryByRole('button', { name: /add line/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /baseline budget/i })).not.toBeInTheDocument();
  });

  it('shows the database error message on load failure', () => {
    isAdminMock.mockReturnValue(true);
    summaryMock.mockReturnValue({ data: undefined, isLoading: false, isError: true, error: new Error('permission denied'), refetch: vi.fn() });
    linesMock.mockReturnValue({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() });
    renderWithRouter(<BudgetTab projectId={P} />);
    expect(screen.getByText(/could not load the budget/i)).toBeInTheDocument();
    expect(screen.getByText('permission denied')).toBeInTheDocument();
  });
});
