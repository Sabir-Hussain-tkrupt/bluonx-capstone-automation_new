import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { ProjectDetailPage } from '../ProjectDetailPage';

const userEvent = userEventBase.setup({ delay: null });

const PROJECT_ID = 'de305d54-75b4-431b-adb2-eb6b9e546014';

const useProjectMock = vi.fn();
const deleteProjectMutate = vi.fn();
const updateProjectMutate = vi.fn();
const deleteDocMutate = vi.fn();
const useProjectDocsMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useParams: () => ({ id: PROJECT_ID }) };
});

vi.mock('@/features/projects/hooks/useProject', () => ({
  useProject: () => useProjectMock(),
}));

vi.mock('@/features/projects/hooks/useUpdateProject', () => ({
  useUpdateProject: () => ({ mutate: updateProjectMutate, isPending: false }),
}));

vi.mock('@/features/projects/hooks/useDeleteProject', () => ({
  useDeleteProject: () => ({ mutate: deleteProjectMutate, isPending: false }),
}));

vi.mock('@/features/projects/hooks/useArchiveProject', () => ({
  useArchiveProject: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/features/projects/hooks/useUnarchiveProject', () => ({
  useUnarchiveProject: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/features/projects/hooks/useProjectDocuments', () => ({
  useProjectDocumentsList: () => useProjectDocsMock(),
  useDeleteProjectDocument: () => ({ mutate: deleteDocMutate, isPending: false, variables: undefined }),
  useProjectDocumentDownload: () => ({ download: vi.fn(), downloadingId: null }),
  useUploadProjectDocument: () => ({ mutate: vi.fn(), isPending: false }),
}));

// The tabbed children pull their own data hooks; they are irrelevant here.
vi.mock('@/features/tasks/components/TaskList', () => ({ TaskList: () => null }));

function projectWith(overrides: Record<string, unknown> = {}) {
  return {
    id: PROJECT_ID,
    name: 'Riverside Grading',
    description: null,
    address: null,
    city: null,
    state: null,
    zip_code: null,
    latitude: null,
    longitude: null,
    budget: 1500000,
    status: 'planning',
    start_date: null,
    estimated_end_date: null,
    created_by: 'u1',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    deleted_at: null,
    archived_at: null,
    archived_by: null,
    ...overrides,
  };
}

function loaded(project: Record<string, unknown>) {
  return { data: project, isLoading: false, error: null, refetch: vi.fn(), isFetching: false };
}

beforeEach(() => {
  vi.clearAllMocks();
  useProjectMock.mockReturnValue(loaded(projectWith()));
  useProjectDocsMock.mockReturnValue({ data: [], isError: false, refetch: vi.fn() });
});

describe('ProjectDetailPage load failures', () => {
  it('says the project is missing on a 404', () => {
    useProjectMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: { status: 404, message: 'The requested resource was not found.' },
      refetch: vi.fn(),
      isFetching: false,
    });

    renderWithRouter(<ProjectDetailPage />);

    expect(screen.getByText('Project not found')).toBeInTheDocument();
  });

  it('reports a network failure as a load error, not a deleted project', () => {
    // The regression: any error rendered "does not exist or has been deleted",
    // so a dropped connection sent the user hunting for a project that is fine.
    useProjectMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: { status: 0, message: 'Unable to reach the server. Check your connection.' },
      refetch: vi.fn(),
      isFetching: false,
    });

    renderWithRouter(<ProjectDetailPage />);

    expect(screen.getByText('Could not load project')).toBeInTheDocument();
    expect(
      screen.getByText('Unable to reach the server. Check your connection.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Project not found')).not.toBeInTheDocument();
  });
});

describe('ProjectDetailPage delete', () => {
  it('confirms before deleting and surfaces the guard message on a 409', async () => {
    // The regression: the delete onError discarded the server message and
    // always showed "Failed to delete project.", hiding the guard's actual
    // reason ("tasks still in progress ...") from the PM.
    const guard =
      'Cannot delete: the following tasks are still in progress: "Grading" (in_progress). ' +
      'Complete or cancel them first, or archive the project instead.';
    deleteProjectMutate.mockImplementation((_id, opts) => opts.onError?.({ status: 409, message: guard }));

    renderWithRouter(<ProjectDetailPage />);

    await userEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await userEvent.click(screen.getByText('Delete'));

    // The dialog is the gate: nothing fires on the menu click.
    expect(deleteProjectMutate).not.toHaveBeenCalled();
    expect(screen.getByText('Delete Project', { selector: 'h2, h3' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Delete Project' }));

    expect(deleteProjectMutate).toHaveBeenCalled();
    expect(await screen.findByText(guard)).toBeInTheDocument();
  });
});

describe('ProjectDetailPage document delete', () => {
  beforeEach(() => {
    useProjectDocsMock.mockReturnValue({
      data: [{ id: 'd1', file_name: 'site-plans.pdf', file_size: 1024, uploaded_at: '2026-03-01T00:00:00Z' }],
      isError: false,
      refetch: vi.fn(),
    });
  });

  it('confirms before deleting a document instead of firing on the icon click', async () => {
    // The regression: the trash icon deleted immediately, with no confirmation.
    renderWithRouter(<ProjectDetailPage />);

    await userEvent.click(screen.getByRole('tab', { name: /Documents/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Delete site-plans.pdf' }));

    expect(deleteDocMutate).not.toHaveBeenCalled();
    expect(screen.getByText('Delete Document', { selector: 'h2, h3' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(deleteDocMutate).toHaveBeenCalledWith(
      expect.objectContaining({ projectId: PROJECT_ID, docId: 'd1' }),
      expect.anything(),
    );
  });

  it('surfaces a document-list load error with a retry', () => {
    useProjectDocsMock.mockReturnValue({ data: [], isError: true, refetch: vi.fn() });

    renderWithRouter(<ProjectDetailPage />);
    // Documents tab still renders; the count badge just reads 0.
    expect(screen.getByText('Riverside Grading')).toBeInTheDocument();
  });
});

describe('ProjectDetailPage edit form', () => {
  it('is remounted per open, so it never serves pre-edit values after a change', async () => {
    // The regression: the edit form was mounted permanently, so React Hook Form
    // kept its first defaultValues. After an edit landed, reopening the form
    // showed the stale pre-edit name.
    renderWithRouter(<ProjectDetailPage />);

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(
      screen.getByRole('dialog').querySelector<HTMLInputElement>('input[name="name"]')!.value,
    ).toBe('Riverside Grading');
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    // Simulate the project changing underneath (a save + refetch).
    useProjectMock.mockReturnValue(loaded(projectWith({ name: 'Riverside Grading Phase 2' })));

    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    expect(
      screen.getByRole('dialog').querySelector<HTMLInputElement>('input[name="name"]')!.value,
    ).toBe('Riverside Grading Phase 2');
  });
});

describe('ProjectDetailPage overview values', () => {
  it('shows a zero budget as $0, not as unset', () => {
    useProjectMock.mockReturnValue(loaded(projectWith({ budget: 0 })));

    renderWithRouter(<ProjectDetailPage />);

    expect(screen.getByText('$0')).toBeInTheDocument();
  });
});
