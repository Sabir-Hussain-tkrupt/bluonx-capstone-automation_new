import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { MilestoneListPage } from '../MilestoneListPage';
import type {
  MilestoneOverviewFilters,
  MilestoneOverviewRow,
} from '@/features/milestones/api/milestoneOverview.queries';

const useMilestoneOverviewMock = vi.fn();
const useProjectsMock = vi.fn();

vi.mock('@/features/milestones/hooks/useMilestoneOverview', () => ({
  useMilestoneOverview: (filters: MilestoneOverviewFilters) =>
    useMilestoneOverviewMock(filters),
}));

vi.mock('@/features/projects/hooks/useProjects', () => ({
  useProjects: () => useProjectsMock(),
}));

function buildRow(): MilestoneOverviewRow {
  return {
    milestone_id: 'ms-1',
    milestone_name: 'Foundation pour',
    status: 'delayed',
    cycle_number: 1,
    sort_order: 0,
    start_date: '2026-06-01',
    end_date: '2026-06-15',
    baseline_end_date: '2026-06-10',
    actual_start_date: null,
    actual_end_date: null,
    end_date_moved: true,
    days_late: null,
    is_overdue: true,
    paused_since: '2026-06-20T00:00:00Z',
    days_paused: 10,
    task_id: 'task-1',
    task_name: 'Grading',
    project_id: 'proj-1',
    project_name: 'Maple Ridge',
    contract_id: 'c-1',
    vendor_id: 'v-1',
    vendor_company_name: 'Apex Grading',
    created_by: 'user-2',
    created_by_name: 'Other PM',
    notes: null,
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-06-20T00:00:00Z',
  };
}

/** The filters passed to the (mocked) query on the most recent render. */
function lastFilters(): MilestoneOverviewFilters {
  return useMilestoneOverviewMock.mock.calls.at(-1)![0];
}

function statusSelect(): HTMLElement {
  const combos = screen.getAllByRole('combobox');
  const found = combos.find((c) => within(c).queryByText('Attention needed'));
  if (!found) throw new Error('status select not found');
  return found;
}

describe('MilestoneListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useMilestoneOverviewMock.mockReturnValue({
      data: { items: [buildRow()], total: 60, page: 1, page_size: 25 },
      isLoading: false,
    });
    useProjectsMock.mockReturnValue({
      data: { items: [{ id: 'proj-1', name: 'Maple Ridge' }] },
    });
  });

  it('defaults to the stalled-first sort (days_paused desc)', () => {
    renderWithRouter(<MilestoneListPage />, { initialEntries: ['/milestones'] });
    expect(lastFilters()).toMatchObject({ sort_by: 'days_paused', sort_dir: 'desc', page: 1 });
  });

  it('defaults the status filter to "Attention needed" on a plain landing', () => {
    renderWithRouter(<MilestoneListPage />, { initialEntries: ['/milestones'] });
    expect(lastFilters().status).toBe('attention');
    expect(within(statusSelect()).getByText('Attention needed').closest('option')).toHaveProperty(
      'selected',
      true,
    );
  });

  it('passes the selected status filter to the query and resets to page 1', async () => {
    const user = userEvent.setup();
    renderWithRouter(<MilestoneListPage />, { initialEntries: ['/milestones'] });

    await user.selectOptions(statusSelect(), 'completed');

    expect(lastFilters()).toMatchObject({ status: 'completed', page: 1 });
  });

  it('sorts server-side when a column header is clicked', async () => {
    const user = userEvent.setup();
    renderWithRouter(<MilestoneListPage />, { initialEntries: ['/milestones'] });

    await user.click(screen.getByRole('button', { name: /^Milestone/i }));

    expect(lastFilters()).toMatchObject({ sort_by: 'milestone_name', sort_dir: 'asc' });
  });

  it('advances the page via pagination', async () => {
    const user = userEvent.setup();
    renderWithRouter(<MilestoneListPage />, { initialEntries: ['/milestones'] });

    await user.click(screen.getByRole('button', { name: /next page/i }));

    expect(lastFilters().page).toBe(2);
  });

  it('shows the committed baseline when the end date has moved', () => {
    renderWithRouter(<MilestoneListPage />, { initialEntries: ['/milestones'] });
    // Rendered in both the desktop table and the mobile card view.
    expect(screen.getAllByText(/committed/i).length).toBeGreaterThan(0);
  });
});
