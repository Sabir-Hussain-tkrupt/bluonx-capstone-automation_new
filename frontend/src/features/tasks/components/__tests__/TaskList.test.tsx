import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { TaskList } from '../TaskList';
import { makeApiError } from '@/test/api-error';

const userEvent = userEventBase.setup({ delay: null });

const useTasksMock = vi.fn();
const deleteMutate = vi.fn();

vi.mock('@/features/tasks/hooks/useTasks', () => ({ useTasks: () => useTasksMock() }));
vi.mock('@/features/tasks/hooks/useCreateTask', () => ({ useCreateTask: () => ({ mutate: vi.fn(), isPending: false }) }));
vi.mock('@/features/tasks/hooks/useUpdateTask', () => ({ useUpdateTask: () => ({ mutate: vi.fn(), isPending: false }) }));
vi.mock('@/features/tasks/hooks/useDeleteTask', () => ({ useDeleteTask: () => ({ mutate: deleteMutate, isPending: false }) }));
vi.mock('@/features/tasks/hooks/useReorderTasks', () => ({ useReorderTasks: () => ({ mutate: vi.fn(), isPending: false }) }));

// The task form and drag-and-drop row are not under test here.
vi.mock('../TaskForm', () => ({ TaskForm: () => null }));
vi.mock('../SortableTaskRow', () => ({
  SortableTaskRow: ({ task, onDelete }: { task: { id: string; name: string }; onDelete: (t: unknown) => void }) => (
    <tr>
      <td>
        <button type="button" onClick={() => onDelete(task)}>Delete {task.name}</button>
      </td>
    </tr>
  ),
  TaskRowOverlay: () => null,
}));

function task(over: Record<string, unknown> = {}) {
  return { id: 't1', name: 'Mass Grading', budget_estimate: 1000, sort_order: 1, ...over };
}

const success = (items: unknown[]) => ({
  data: { items, total: items.length, page: 1, page_size: 100 },
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
  isFetching: false,
});

beforeEach(() => {
  vi.clearAllMocks();
  useTasksMock.mockReturnValue(success([]));
});

describe('TaskList load failures', () => {
  it('reports a failed fetch with a retry instead of a bare message', async () => {
    const refetch = vi.fn();
    useTasksMock.mockReturnValue({
      ...success([]),
      data: undefined,
      isError: true,
      error: makeApiError('Unable to reach the server.', 0, 'NETWORK_ERROR'),
      refetch,
    });

    renderWithRouter(<TaskList projectId="p1" />);

    expect(screen.getByText('Could not load tasks')).toBeInTheDocument();
    expect(screen.getByText('Unable to reach the server.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalled();
  });
});

describe('TaskList delete', () => {
  it('confirms before deleting and surfaces the 409 guard message', async () => {
    // The regression targets: delete used to fire from a bare Modal, and its
    // onError discarded the server message.
    const guard = 'Cannot delete task: it has active bid packages. Cancel the task instead to preserve its history.';
    deleteMutate.mockImplementation((_id, opts) =>
      opts.onError?.(makeApiError(guard, 409, 'CONFLICT')),
    );
    useTasksMock.mockReturnValue(success([task()]));

    renderWithRouter(<TaskList projectId="p1" />);

    await userEvent.click(screen.getByRole('button', { name: 'Delete Mass Grading' }));

    // The dialog is the gate: nothing fired on the row click.
    expect(deleteMutate).not.toHaveBeenCalled();
    expect(screen.getByText('Delete Task', { selector: 'h2, h3' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Delete Task' }));

    expect(deleteMutate).toHaveBeenCalled();
    expect(await screen.findByText(guard)).toBeInTheDocument();
  });
});
