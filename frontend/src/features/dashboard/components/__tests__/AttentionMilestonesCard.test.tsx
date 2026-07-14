import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { AttentionMilestonesCard } from '../AttentionMilestonesCard';
import type { MilestoneOverviewRow } from '@/features/milestones/api/milestoneOverview.queries';

const usePausedMilestonesMock = vi.fn();

vi.mock('@/features/dashboard/hooks/usePausedMilestones', () => ({
  usePausedMilestones: () => usePausedMilestonesMock(),
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ profile: { id: 'user-1', full_name: 'Me', role: 'project_manager' } }),
}));

function buildRow(overrides: Partial<MilestoneOverviewRow> = {}): MilestoneOverviewRow {
  return {
    milestone_id: 'ms-1',
    milestone_name: 'Foundation pour',
    status: 'delayed',
    cycle_number: 1,
    sort_order: 0,
    start_date: '2026-06-01',
    end_date: '2026-06-15',
    baseline_end_date: '2026-06-15',
    actual_start_date: null,
    actual_end_date: null,
    end_date_moved: false,
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
    ...overrides,
  };
}

describe('AttentionMilestonesCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders paused milestones in the given (days_paused DESC) order', () => {
    usePausedMilestonesMock.mockReturnValue({
      data: [
        buildRow({ milestone_id: 'a', milestone_name: 'Stalled long', days_paused: 21 }),
        buildRow({ milestone_id: 'b', milestone_name: 'Stalled short', days_paused: 3 }),
      ],
      isLoading: false,
    });

    renderWithRouter(<AttentionMilestonesCard />);

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText('Stalled long')).toBeInTheDocument();
    expect(within(items[1]).getByText('Stalled short')).toBeInTheDocument();
    expect(screen.getByText('stalled 21 days')).toBeInTheDocument();
  });

  it('renders the good-news empty state when nothing is paused', () => {
    usePausedMilestonesMock.mockReturnValue({ data: [], isLoading: false });
    renderWithRouter(<AttentionMilestonesCard />);
    expect(screen.getByText(/nothing is waiting on you/i)).toBeInTheDocument();
  });

  it('marks the current user\'s rows with a "You" badge', () => {
    usePausedMilestonesMock.mockReturnValue({
      data: [buildRow({ created_by: 'user-1', created_by_name: 'Me' })],
      isLoading: false,
    });
    renderWithRouter(<AttentionMilestonesCard />);
    expect(screen.getByText('You')).toBeInTheDocument();
  });

  it('"Mine only" toggle filters to milestones created by the current user', async () => {
    const user = userEvent.setup();
    usePausedMilestonesMock.mockReturnValue({
      data: [
        buildRow({ milestone_id: 'mine', milestone_name: 'My milestone', created_by: 'user-1' }),
        buildRow({ milestone_id: 'theirs', milestone_name: 'Their milestone', created_by: 'user-2' }),
      ],
      isLoading: false,
    });

    renderWithRouter(<AttentionMilestonesCard />);

    // Both visible by default (toggle OFF).
    expect(screen.getByText('My milestone')).toBeInTheDocument();
    expect(screen.getByText('Their milestone')).toBeInTheDocument();

    await user.click(screen.getByLabelText(/mine only/i));

    expect(screen.getByText('My milestone')).toBeInTheDocument();
    expect(screen.queryByText('Their milestone')).not.toBeInTheDocument();
  });
});
