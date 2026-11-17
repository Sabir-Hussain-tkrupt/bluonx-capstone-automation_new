import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { NotesTab } from '../NotesTab';
import type { ProjectNote } from '../../api/note.api';

const userEvent = userEventBase.setup({ delay: null });
const createMutate = vi.fn();
const updateMutate = vi.fn();
const deleteMutate = vi.fn();
let notes: ProjectNote[] = [];

vi.mock('../../hooks/useNotes', () => ({
  useNotes: () => ({ data: notes, isLoading: false, isError: false, refetch: vi.fn() }),
  useCreateNote: () => ({ mutate: createMutate, isPending: false }),
  useUpdateNote: () => ({ mutate: updateMutate, isPending: false }),
  useDeleteNote: () => ({ mutate: deleteMutate, isPending: false }),
}));

// The real editor is exercised in RichTextEditor.test; a textarea stands in here.
vi.mock('@/components/shared/RichTextEditor', () => ({
  RichTextEditor: ({ initialContent, onChange }: { initialContent?: string; onChange?: (h: string, t: string) => void }) => (
    <textarea
      aria-label="Note content"
      defaultValue={initialContent}
      onChange={(e) => onChange?.(`<p>${e.target.value}</p>`, e.target.value)}
    />
  ),
  RichTextViewer: ({ content }: { content: string }) => <div data-testid="viewer">{content}</div>,
}));

function note(overrides: Partial<ProjectNote> = {}): ProjectNote {
  return {
    id: 'n1',
    project_id: 'p',
    title: 'Kick-off meeting',
    content_html: '<p><strong>Agenda</strong></p>',
    content_text: 'Agenda',
    created_by: 'u1',
    created_by_name: 'Pat PM',
    updated_by: null,
    updated_by_name: null,
    created_at: '2026-11-17T10:00:00Z',
    updated_at: '2026-11-17T10:00:00Z',
    can_edit: true,
    ...overrides,
  };
}

describe('NotesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    notes = [];
  });

  it('shows an empty state with Add Note', () => {
    renderWithRouter(<NotesTab projectId="p" />);
    expect(screen.getByText(/no notes yet/i)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /add note/i }).length).toBeGreaterThan(0);
  });

  it('adds a note with a title and rich content', async () => {
    renderWithRouter(<NotesTab projectId="p" />);
    await userEvent.click(screen.getAllByRole('button', { name: /add note/i })[0]);
    await userEvent.type(screen.getByLabelText(/title/i), 'Site visit');
    await userEvent.type(screen.getByLabelText(/note content/i), 'Drainage looks good');
    await userEvent.click(screen.getAllByRole('button', { name: /save note/i })[0]);
    expect(createMutate).toHaveBeenCalledWith(
      { title: 'Site visit', content_html: '<p>Drainage looks good</p>', content_text: 'Drainage looks good' },
      expect.anything(),
    );
  });

  it('requires a title', async () => {
    renderWithRouter(<NotesTab projectId="p" />);
    await userEvent.click(screen.getAllByRole('button', { name: /add note/i })[0]);
    await userEvent.click(screen.getAllByRole('button', { name: /save note/i })[0]);
    expect(screen.getByText(/title is required/i)).toBeInTheDocument();
    expect(createMutate).not.toHaveBeenCalled();
  });

  it('opens a note and edits it', async () => {
    notes = [note()];
    renderWithRouter(<NotesTab projectId="p" />);
    expect(screen.getByText('Agenda')).toBeInTheDocument();
    await userEvent.click(screen.getByText('Kick-off meeting'));
    expect(screen.getByTestId('viewer')).toHaveTextContent('<p><strong>Agenda</strong></p>');
    await userEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    const title = screen.getByLabelText(/title/i);
    await userEvent.clear(title);
    await userEvent.type(title, 'Kick-off (final)');
    await userEvent.click(screen.getAllByRole('button', { name: /save note/i })[0]);
    expect(updateMutate).toHaveBeenCalledWith(
      { noteId: 'n1', input: expect.objectContaining({ title: 'Kick-off (final)' }) },
      expect.anything(),
    );
  });

  it('hides edit and delete on notes the user cannot change, and on archived projects', () => {
    notes = [note({ can_edit: false })];
    const { unmount } = renderWithRouter(<NotesTab projectId="p" />);
    expect(screen.queryByRole('button', { name: /actions for/i })).not.toBeInTheDocument();
    unmount();
    notes = [note()];
    renderWithRouter(<NotesTab projectId="p" readOnly />);
    expect(screen.queryByRole('button', { name: /add note/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /actions for/i })).not.toBeInTheDocument();
  });

  it('asks before deleting', async () => {
    notes = [note()];
    renderWithRouter(<NotesTab projectId="p" />);
    await userEvent.click(screen.getByText('Kick-off meeting'));
    await userEvent.click(screen.getByRole('button', { name: /delete note/i }));
    await userEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    expect(deleteMutate).toHaveBeenCalledWith('n1', expect.anything());
  });
});
