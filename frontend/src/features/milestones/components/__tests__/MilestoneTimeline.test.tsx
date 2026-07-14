import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { MilestoneTimeline } from '../MilestoneTimeline';
import type { MilestoneOverviewRow } from '@/features/milestones/api/milestoneOverview.queries';

const useProjectTimelineMock = vi.fn();

vi.mock('@/features/milestones/hooks/useProjectTimeline', () => ({
  useProjectTimeline: () => useProjectTimelineMock(),
}));

function buildRow(overrides: Partial<MilestoneOverviewRow> = {}): MilestoneOverviewRow {
  return {
    milestone_id: 'ms-1',
    milestone_name: 'Foundation pour',
    status: 'scheduled',
    cycle_number: 1,
    sort_order: 0,
    start_date: '2026-06-01',
    end_date: '2026-06-15',
    baseline_end_date: '2026-06-15',
    actual_start_date: null,
    actual_end_date: null,
    end_date_moved: false,
    days_late: null,
    is_overdue: false,
    paused_since: null,
    days_paused: null,
    task_id: 'task-1',
    task_name: 'Grading',
    project_id: 'proj-1',
    project_name: 'Maple Ridge',
    contract_id: 'c-1',
    vendor_id: 'v-1',
    vendor_company_name: 'Apex Grading',
    created_by: 'user-1',
    created_by_name: 'PM',
    notes: null,
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-06-01T00:00:00Z',
    ...overrides,
  };
}

describe('MilestoneTimeline', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the empty state with zero milestones', () => {
    useProjectTimelineMock.mockReturnValue({ data: [], isLoading: false });
    renderWithRouter(<MilestoneTimeline projectId="proj-1" />);
    expect(screen.getByText(/no milestones yet/i)).toBeInTheDocument();
  });

  it('renders a single milestone without crashing (no divide-by-zero)', () => {
    useProjectTimelineMock.mockReturnValue({ data: [buildRow()], isLoading: false });
    renderWithRouter(<MilestoneTimeline projectId="proj-1" />);
    expect(screen.getByText('Foundation pour')).toBeInTheDocument();
    expect(screen.getByText('Grading')).toBeInTheDocument();
  });

  it('renders multiple milestones grouped by task', () => {
    useProjectTimelineMock.mockReturnValue({
      data: [
        buildRow({ milestone_id: 'a', milestone_name: 'Pour A', task_id: 't1', task_name: 'Task One' }),
        buildRow({ milestone_id: 'b', milestone_name: 'Pour B', task_id: 't1', task_name: 'Task One' }),
        buildRow({ milestone_id: 'c', milestone_name: 'Pour C', task_id: 't2', task_name: 'Task Two' }),
      ],
      isLoading: false,
    });
    renderWithRouter(<MilestoneTimeline projectId="proj-1" />);
    expect(screen.getByText('Pour A')).toBeInTheDocument();
    expect(screen.getByText('Pour C')).toBeInTheDocument();
    expect(screen.getByText('Task One')).toBeInTheDocument();
    expect(screen.getByText('Task Two')).toBeInTheDocument();
  });

  it('shows the committed-baseline marker only when the end date has moved', () => {
    useProjectTimelineMock.mockReturnValue({
      data: [buildRow({ end_date_moved: false })],
      isLoading: false,
    });
    const { unmount } = renderWithRouter(<MilestoneTimeline projectId="proj-1" />);
    expect(screen.queryByLabelText(/committed end/i)).not.toBeInTheDocument();
    unmount();

    useProjectTimelineMock.mockReturnValue({
      data: [buildRow({ end_date_moved: true, baseline_end_date: '2026-06-10' })],
      isLoading: false,
    });
    renderWithRouter(<MilestoneTimeline projectId="proj-1" />);
    expect(screen.getByLabelText(/committed end/i)).toBeInTheDocument();
  });
});
