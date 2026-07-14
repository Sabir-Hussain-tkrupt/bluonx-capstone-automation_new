import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { AttentionMilestonesCard } from '../AttentionMilestonesCard';
import type {
  MilestoneOverviewRow,
  PausedMilestonesParams,
} from '@/features/milestones/api/milestoneOverview.queries';

const usePausedMilestonesMock = vi.fn();
const usePausedMilestonesCountMock = vi.fn();

vi.mock('@/features/dashboard/hooks/usePausedMilestones', () => ({
  usePausedMilestones: (params: PausedMilestonesParams) => usePausedMilestonesMock(params),
  usePausedMilestonesCount: (createdBy?: string) => usePausedMilestonesCountMock(createdBy),
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

/** Convenience: set both mocked hooks for a plain (not-mine) render. */
function mockPaused(rows: MilestoneOverviewRow[], total = rows.length) {
  usePausedMilestonesMock.mockReturnValue({ data: rows, isLoading: false });
  usePausedMilestonesCountMock.mockReturnValue({ data: total });
}

describe('AttentionMilestonesCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders paused milestones in the given (days_paused DESC) order', () => {
    mockPaused([
      buildRow({ milestone_id: 'a', milestone_name: 'Stalled long', days_paused: 21 }),
      buildRow({ milestone_id: 'b', milestone_name: 'Stalled short', days_paused: 3 }),
    ]);

    renderWithRouter(<AttentionMilestonesCard />);

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText('Stalled long')).toBeInTheDocument();
    expect(within(items[1]).getByText('Stalled short')).toBeInTheDocument();
    expect(screen.getByText('stalled 21 days')).toBeInTheDocument();
  });

  it('requests only MAX_ROWS rows from the server (does not fetch everything)', () => {
    mockPaused([buildRow()], 42);
    renderWithRouter(<AttentionMilestonesCard />);
    expect(usePausedMilestonesMock).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 5, createdBy: undefined }),
    );
  });

  it('shows the true total from the count query and a "View all" link when it exceeds the cap', () => {
    mockPaused([buildRow(), buildRow({ milestone_id: 'x' })], 42);
    renderWithRouter(<AttentionMilestonesCard />);
    // Header count chip + "View all 42" both reflect the count, not the fetched rows.
    expect(screen.getByText('View all 42')).toBeInTheDocument();
  });

  it('renders the good-news empty state when nothing is paused', () => {
    mockPaused([], 0);
    renderWithRouter(<AttentionMilestonesCard />);
    expect(screen.getByText(/nothing is waiting on you/i)).toBeInTheDocument();
  });

  it('marks the current user\'s rows with a "You" badge', () => {
    mockPaused([buildRow({ created_by: 'user-1', created_by_name: 'Me' })], 1);
    renderWithRouter(<AttentionMilestonesCard />);
    expect(screen.getByText('You')).toBeInTheDocument();
  });

  it('"Mine only" toggle scopes the query to the current user (server-side)', async () => {
    const user = userEvent.setup();

    usePausedMilestonesMock.mockImplementation((params: PausedMilestonesParams) => ({
      data: params?.createdBy
        ? [buildRow({ milestone_id: 'mine', milestone_name: 'My milestone', created_by: 'user-1' })]
        : [
            buildRow({ milestone_id: 'mine', milestone_name: 'My milestone', created_by: 'user-1' }),
            buildRow({ milestone_id: 'theirs', milestone_name: 'Their milestone', created_by: 'user-2' }),
          ],
      isLoading: false,
    }));
    usePausedMilestonesCountMock.mockImplementation((createdBy?: string) => ({
      data: createdBy ? 1 : 2,
    }));

    renderWithRouter(<AttentionMilestonesCard />);

    // Both visible by default (toggle OFF).
    expect(screen.getByText('My milestone')).toBeInTheDocument();
    expect(screen.getByText('Their milestone')).toBeInTheDocument();

    await user.click(screen.getByLabelText(/mine only/i));

    // Query re-scoped to the current user; the other PM's row is gone.
    expect(usePausedMilestonesMock).toHaveBeenCalledWith(
      expect.objectContaining({ createdBy: 'user-1', limit: 5 }),
    );
    expect(usePausedMilestonesCountMock).toHaveBeenCalledWith('user-1');
    expect(screen.getByText('My milestone')).toBeInTheDocument();
    expect(screen.queryByText('Their milestone')).not.toBeInTheDocument();
  });
});
