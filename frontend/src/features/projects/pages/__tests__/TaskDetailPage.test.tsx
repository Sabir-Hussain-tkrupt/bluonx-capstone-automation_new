import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { TaskDetailPage } from '../TaskDetailPage';
import { makeApiError } from '@/test/api-error';

const userEvent = userEventBase.setup({ delay: null });

const PROJECT_ID = 'p1';
const TASK_ID = 't1';

const useTaskMock = vi.fn();
const deleteMutate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useParams: () => ({ id: PROJECT_ID, taskId: TASK_ID }) };
});

vi.mock('@/features/tasks/hooks/useTask', () => ({ useTask: () => useTaskMock() }));
vi.mock('@/features/projects/hooks/useProject', () => ({ useProject: () => ({ data: { archived_at: null } }) }));
vi.mock('@/features/tasks/hooks/useUpdateTask', () => ({ useUpdateTask: () => ({ mutate: vi.fn(), isPending: false }) }));
vi.mock('@/features/tasks/hooks/useDeleteTask', () => ({ useDeleteTask: () => ({ mutate: deleteMutate, isPending: false }) }));
vi.mock('@/features/bids/hooks/useBidPackagesForTask', () => ({ useBidPackagesForTask: () => ({ data: [], isLoading: false }) }));
vi.mock('@/features/milestones/hooks/useTaskContractState', () => ({ useTaskContractState: () => ({ data: undefined }) }));
vi.mock('@/features/tasks/components/TaskForm', () => ({ TaskForm: () => null }));

function taskWith(over: Record<string, unknown> = {}) {
  return {
    id: TASK_ID,
    project_id: PROJECT_ID,
    trade_id: 'trade-dev',
    name: 'Mass Grading',
    description: null,
    phase: 'development',
    bid_type: 'internal',
    budget_estimate: 5000,
    sort_order: 1,
    status: 'draft',
    trade_name: 'Grading',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    deleted_at: null,
    ...over,
  };
}

const loaded = (task: Record<string, unknown>) => ({
  data: task,
  isLoading: false,
  error: null,
  refetch: vi.fn(),
  isFetching: false,
});

beforeEach(() => {
  vi.clearAllMocks();
  useTaskMock.mockReturnValue(loaded(taskWith()));
});

describe('TaskDetailPage load failures', () => {
  it('says the task is missing on a 404', () => {
    useTaskMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: makeApiError('The requested resource was not found.', 404, 'NOT_FOUND'),
      refetch: vi.fn(),
      isFetching: false,
    });

    renderWithRouter(<TaskDetailPage />);
    expect(screen.getByText('Task not found')).toBeInTheDocument();
  });

  it('reports a network failure as a load error, not a deleted task', () => {
    useTaskMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: makeApiError('Unable to reach the server.', 0, 'NETWORK_ERROR'),
      refetch: vi.fn(),
      isFetching: false,
    });

    renderWithRouter(<TaskDetailPage />);
    expect(screen.getByText('Could not load task')).toBeInTheDocument();
    expect(screen.getByText('Unable to reach the server.')).toBeInTheDocument();
    expect(screen.queryByText('Task not found')).not.toBeInTheDocument();
  });
});

describe('TaskDetailPage delete', () => {
  it('confirms before deleting and surfaces the 409 guard message', async () => {
    const guard = 'Cannot delete task: it has active bid packages. Cancel the task instead to preserve its history.';
    deleteMutate.mockImplementation((_id, opts) =>
      opts.onError?.(makeApiError(guard, 409, 'CONFLICT')),
    );

    renderWithRouter(<TaskDetailPage />);

    await userEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await userEvent.click(screen.getByText('Delete'));

    expect(deleteMutate).not.toHaveBeenCalled();
    expect(screen.getByText('Delete Task', { selector: 'h2, h3' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Delete Task' }));

    expect(deleteMutate).toHaveBeenCalled();
    expect(await screen.findByText(guard)).toBeInTheDocument();
  });
});

describe('TaskDetailPage legacy direct_assign', () => {
  it('still renders the Direct Assign label for a legacy task', () => {
    useTaskMock.mockReturnValue(loaded(taskWith({ bid_type: 'direct_assign' })));

    renderWithRouter(<TaskDetailPage />);
    expect(screen.getByText('Direct Assign')).toBeInTheDocument();
  });
});
