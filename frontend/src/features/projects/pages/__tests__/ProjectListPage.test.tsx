import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';

const userEvent = userEventBase.setup({ delay: null });
import { renderWithRouter } from '@/test/test-utils';
import { ProjectListPage } from '../ProjectListPage';

const useProjectsMock = vi.fn();
const createMutateMock = vi.fn();

vi.mock('@/features/projects/hooks/useProjects', () => ({
  useProjects: () => useProjectsMock(),
}));

vi.mock('@/features/projects/hooks/useCreateProject', () => ({
  useCreateProject: () => ({ mutate: createMutateMock, isPending: false }),
}));

const emptySuccess = {
  data: { items: [], total: 0, page: 1, page_size: 25 },
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
  isFetching: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  useProjectsMock.mockReturnValue(emptySuccess);
});

describe('ProjectListPage load failures', () => {
  it('reports a failed fetch instead of claiming there are no projects', () => {
    // The regression: isError was dropped, so a dead API or an expired session
    // rendered "No projects found — try adjusting your filters", pointing the
    // user at a filter that was never the problem.
    useProjectsMock.mockReturnValue({
      ...emptySuccess,
      data: undefined,
      isError: true,
      error: { message: 'Unable to reach the server. Check your connection.', status: 0 },
    });

    renderWithRouter(<ProjectListPage />);

    expect(screen.getByText('Could not load projects')).toBeInTheDocument();
    expect(
      screen.getByText('Unable to reach the server. Check your connection.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('No projects found')).not.toBeInTheDocument();
  });

  it('offers a retry that refetches', async () => {
    const refetch = vi.fn();
    useProjectsMock.mockReturnValue({
      ...emptySuccess,
      data: undefined,
      isError: true,
      error: { message: 'Server error', status: 500 },
      refetch,
    });

    renderWithRouter(<ProjectListPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(refetch).toHaveBeenCalled();
  });

  it('still shows the ordinary empty state when the fetch succeeded with no rows', () => {
    renderWithRouter(<ProjectListPage />);

    expect(screen.getByText('No projects found')).toBeInTheDocument();
    expect(screen.queryByText('Could not load projects')).not.toBeInTheDocument();
  });
});

describe('ProjectListPage create form', () => {
  it('is not mounted until opened, and opens empty again after a create', async () => {
    // The regression: the form was mounted permanently, so React Hook Form's
    // mount-time defaultValues survived a close and a reopened form could serve
    // the values just submitted.
    createMutateMock.mockImplementation((_input, opts) => opts.onSuccess?.());

    renderWithRouter(<ProjectListPage />);

    // Absent until opened.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '+ New Project' }));
    const dialog = screen.getByRole('dialog');
    const nameInput = dialog.querySelector<HTMLInputElement>('input[name="name"]')!;
    await userEvent.type(nameInput, 'Riverside Grading');
    await userEvent.click(screen.getByRole('button', { name: 'Create Project' }));

    expect(createMutateMock).toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    // Reopen: a fresh form, not the record we just created.
    await userEvent.click(screen.getByRole('button', { name: '+ New Project' }));
    const reopened = screen.getByRole('dialog');
    expect(reopened.querySelector<HTMLInputElement>('input[name="name"]')!.value).toBe('');
  });
});
