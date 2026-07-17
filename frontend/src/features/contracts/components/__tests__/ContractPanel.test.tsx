import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { ContractPanel } from '../ContractPanel';
import type { Milestone } from '@/features/milestones/api/milestone.queries';
import type { TaskActiveContract } from '@/features/milestones/api/milestone.queries';

const useMilestonesForTaskMock = vi.fn();
const markMutateMock = vi.fn();
const useContractReviewMock = vi.fn();

vi.mock('@/features/milestones/hooks/useMilestonesForTask', () => ({
  useMilestonesForTask: () => useMilestonesForTaskMock(),
}));
vi.mock('@/features/contracts/hooks/useMarkContractComplete', () => ({
  useMarkContractComplete: () => ({ mutate: markMutateMock, isPending: false }),
}));
vi.mock('@/features/contracts/hooks/useContractReview', () => ({
  useContractReview: () => useContractReviewMock(),
}));

function milestone(overrides: Partial<Milestone> = {}): Milestone {
  return {
    id: 'm-1',
    task_id: 'task-1',
    contract_id: 'c-1',
    name: 'Foundation',
    start_date: '2026-06-01',
    end_date: '2026-06-15',
    baseline_end_date: '2026-06-15',
    actual_start_date: null,
    actual_end_date: null,
    status: 'completed',
    cycle_number: 1,
    sort_order: 0,
    notes: null,
    created_by: 'u-1',
    created_at: '2026-05-01T00:00:00Z',
    updated_at: '2026-06-01T00:00:00Z',
    ...overrides,
  };
}

function contract(overrides: Partial<TaskActiveContract> = {}): TaskActiveContract {
  return {
    id: 'c-1',
    status: 'executed',
    contract_number: 'CON-2026-ABCD1234',
    start_date: null,
    end_date: null,
    ...overrides,
  };
}

describe('ContractPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useContractReviewMock.mockReturnValue({ data: null, isLoading: false });
  });

  it('shows Mark complete when all milestones are done', () => {
    useMilestonesForTaskMock.mockReturnValue({
      data: [milestone({ status: 'completed' }), milestone({ id: 'm-2', status: 'cancelled' })],
      isLoading: false,
    });
    renderWithRouter(<ContractPanel taskId="task-1" contract={contract()} />);
    expect(screen.getByRole('button', { name: /mark contract complete/i })).toBeInTheDocument();
  });

  it('hides Mark complete when a milestone is still open', () => {
    useMilestonesForTaskMock.mockReturnValue({
      data: [milestone({ status: 'in_progress' })],
      isLoading: false,
    });
    renderWithRouter(<ContractPanel taskId="task-1" contract={contract()} />);
    expect(
      screen.queryByRole('button', { name: /mark contract complete/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/complete or cancel every milestone/i)).toBeInTheDocument();
  });

  it('does not show Mark complete while milestones are still loading', () => {
    // Empty array + isLoading:true must NOT read as "all done" (vacuous every()).
    useMilestonesForTaskMock.mockReturnValue({ data: [], isLoading: true });
    renderWithRouter(<ContractPanel taskId="task-1" contract={contract()} />);
    expect(
      screen.queryByRole('button', { name: /mark contract complete/i }),
    ).not.toBeInTheDocument();
  });

  it('shows the rating panel once the contract is completed', () => {
    useMilestonesForTaskMock.mockReturnValue({
      data: [milestone({ status: 'completed' })],
      isLoading: false,
    });
    renderWithRouter(
      <ContractPanel taskId="task-1" contract={contract({ status: 'completed' })} />,
    );
    // No mark-complete button once completed; the soft rating prompt appears instead.
    expect(
      screen.queryByRole('button', { name: /mark contract complete/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/rate this vendor/i)).toBeInTheDocument();
  });
});
