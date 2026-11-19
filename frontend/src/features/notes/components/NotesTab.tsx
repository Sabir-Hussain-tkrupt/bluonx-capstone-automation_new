import { useState } from 'react';
import { ArrowLeft, FileText, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { DropdownMenu, DropdownMenuItem } from '@/components/ui/DropdownMenu';
import { EmptyState } from '@/components/ui/EmptyState';
import { FormField } from '@/components/ui/FormField';
import { IconButton } from '@/components/ui/IconButton';
import { Skeleton } from '@/components/ui/Skeleton';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast/useToast';
import { RichTextEditor, RichTextViewer } from '@/components/shared/RichTextEditor';
import { errorMessage } from '@/lib/api';
import type { ProjectNote } from '../api/note.api';
import { useCreateNote, useDeleteNote, useNotes, useUpdateNote } from '../hooks/useNotes';

interface NotesTabProps {
  projectId: string;
  readOnly?: boolean;
}

type View =
  | { kind: 'list' }
  | { kind: 'view'; noteId: string }
  | { kind: 'edit'; noteId: string }
  | { kind: 'new' };

function formatNoteTime(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

function noteMeta(note: ProjectNote): string {
  const author = note.created_by_name ?? 'Unknown';
  const edited = note.updated_at && note.updated_at !== note.created_at;
  return edited
    ? `By ${author} · updated ${formatNoteTime(note.updated_at)}${note.updated_by_name && note.updated_by_name !== author ? ` by ${note.updated_by_name}` : ''}`
    : `By ${author} · ${formatNoteTime(note.created_at)}`;
}

// ── Editor (mounted fresh per note, so its state starts from that note) ──

interface NoteEditorProps {
  note?: ProjectNote;
  isSaving: boolean;
  onSave: (input: { title: string; content_html: string; content_text: string }) => void;
  onCancel: () => void;
}

function NoteEditor({ note, isSaving, onSave, onCancel }: NoteEditorProps) {
  const [title, setTitle] = useState(note?.title ?? '');
  const [html, setHtml] = useState(note?.content_html ?? '');
  const [text, setText] = useState(note?.content_text ?? '');
  const [titleError, setTitleError] = useState<string | undefined>();
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const dirty =
    title !== (note?.title ?? '') || html !== (note?.content_html ?? '');

  const save = () => {
    const cleaned = title.trim();
    if (!cleaned) {
      setTitleError('Title is required');
      return;
    }
    if (cleaned.length > 255) {
      setTitleError('Title must be 255 characters or fewer');
      return;
    }
    onSave({ title: cleaned, content_html: html, content_text: text });
  };

  const cancel = () => (dirty ? setConfirmDiscard(true) : onCancel());

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-lg font-semibold text-secondary-900">{note ? 'Edit Note' : 'New Note'}</h2>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={cancel} disabled={isSaving}>Cancel</Button>
          <Button size="sm" onClick={save} isLoading={isSaving}>Save Note</Button>
        </div>
      </div>

      <FormField label="Title" required error={titleError} htmlFor="note-title">
        <TextInput
          id="note-title"
          value={title}
          maxLength={255}
          autoFocus={!note}
          placeholder="e.g. Site visit — Nov 17"
          error={titleError}
          onChange={(e) => {
            setTitle(e.target.value);
            if (titleError) setTitleError(undefined);
          }}
        />
      </FormField>

      <RichTextEditor
        initialContent={note?.content_html ?? ''}
        autoFocus={!!note}
        placeholder="Write your note… Use the toolbar for headings, bold, italic, lists and more."
        onChange={(h, t) => {
          setHtml(h);
          setText(t);
        }}
      />

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={cancel} disabled={isSaving}>Cancel</Button>
        <Button onClick={save} isLoading={isSaving}>Save Note</Button>
      </div>

      <ConfirmDialog
        isOpen={confirmDiscard}
        title="Discard changes?"
        message="Your unsaved changes to this note will be lost."
        confirmText="Discard"
        confirmVariant="danger"
        onConfirm={() => {
          setConfirmDiscard(false);
          onCancel();
        }}
        onCancel={() => setConfirmDiscard(false)}
      />
    </div>
  );
}

// ── Tab ────────────────────────────────────────────────────────────────

/**
 * Project notes: free-form, document-sized rich-text notes (meeting minutes,
 * site observations, decisions). Anyone can add a note; the author or an
 * admin can edit or delete it. Archived projects are read-only.
 */
export function NotesTab({ projectId, readOnly = false }: NotesTabProps) {
  const { toast } = useToast();
  const { data: notes = [], isLoading, isError, refetch } = useNotes(projectId);
  const createMutation = useCreateNote(projectId);
  const updateMutation = useUpdateNote(projectId);
  const deleteMutation = useDeleteNote(projectId);

  const [view, setView] = useState<View>({ kind: 'list' });
  const [deleteTarget, setDeleteTarget] = useState<ProjectNote | null>(null);

  const current =
    view.kind === 'view' || view.kind === 'edit' ? notes.find((n) => n.id === view.noteId) : undefined;

  const confirmDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast({ variant: 'success', message: 'Note deleted.' });
        setDeleteTarget(null);
        setView({ kind: 'list' });
      },
      onError: (error) => {
        toast({ variant: 'danger', message: errorMessage(error, 'Could not delete the note.') });
        setDeleteTarget(null);
      },
    });
  };

  const deleteDialog = (
    <ConfirmDialog
      isOpen={!!deleteTarget}
      title="Delete note?"
      message={<>“{deleteTarget?.title}” will be removed from this project.</>}
      confirmText="Delete"
      confirmVariant="danger"
      isLoading={deleteMutation.isPending}
      onConfirm={confirmDelete}
      onCancel={() => setDeleteTarget(null)}
    />
  );

  // ── New / edit ──
  if (view.kind === 'new' && !readOnly) {
    return (
      <NoteEditor
        key="new"
        isSaving={createMutation.isPending}
        onCancel={() => setView({ kind: 'list' })}
        onSave={(input) =>
          createMutation.mutate(input, {
            onSuccess: (created) => {
              toast({ variant: 'success', message: 'Note saved.' });
              setView({ kind: 'view', noteId: created.id });
            },
            onError: (error) => toast({ variant: 'danger', message: errorMessage(error, 'Could not save the note.') }),
          })
        }
      />
    );
  }

  if (view.kind === 'edit' && current && current.can_edit && !readOnly) {
    return (
      <NoteEditor
        key={current.id}
        note={current}
        isSaving={updateMutation.isPending}
        onCancel={() => setView({ kind: 'view', noteId: current.id })}
        onSave={(input) =>
          updateMutation.mutate(
            { noteId: current.id, input },
            {
              onSuccess: () => {
                toast({ variant: 'success', message: 'Note updated.' });
                setView({ kind: 'view', noteId: current.id });
              },
              onError: (error) => toast({ variant: 'danger', message: errorMessage(error, 'Could not save the note.') }),
            },
          )
        }
      />
    );
  }

  // ── Single note ──
  if ((view.kind === 'view' || view.kind === 'edit') && current) {
    const canChange = current.can_edit && !readOnly;
    return (
      <div className="space-y-4">
        <button
          type="button"
          onClick={() => setView({ kind: 'list' })}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-secondary-600 hover:text-secondary-900"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" /> All notes
        </button>
        <Card padding="lg">
          <div className="mb-6 flex items-start justify-between gap-4 border-b border-secondary-200 pb-4">
            <div className="min-w-0">
              <h2 className="break-words text-xl font-semibold text-secondary-900">{current.title}</h2>
              <p className="mt-1 text-sm text-secondary-500">{noteMeta(current)}</p>
            </div>
            {canChange && (
              <div className="flex shrink-0 items-center gap-2">
                <Button variant="outline" size="sm" leftIcon={<Pencil className="h-4 w-4" />} onClick={() => setView({ kind: 'edit', noteId: current.id })}>
                  Edit
                </Button>
                <IconButton
                  icon={<Trash2 className="h-4 w-4" />}
                  aria-label="Delete note"
                  variant="ghost"
                  size="sm"
                  onClick={() => setDeleteTarget(current)}
                />
              </div>
            )}
          </div>
          {current.content_html ? (
            <RichTextViewer content={current.content_html} />
          ) : (
            <p className="text-sm italic text-secondary-400">This note has no content yet.</p>
          )}
        </Card>
        {deleteDialog}
      </div>
    );
  }

  // ── List ──
  return (
    <div className="space-y-4">
      {!readOnly && (
        <div className="flex justify-end">
          <Button size="sm" onClick={() => setView({ kind: 'new' })}>+ Add Note</Button>
        </div>
      )}

      {isError && (
        <Alert variant="danger" title="Could not load notes">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>The notes for this project could not be loaded.</span>
            <Button variant="outline" size="sm" onClick={() => refetch()}>Retry</Button>
          </div>
        </Alert>
      )}

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : !isError && notes.length === 0 ? (
        <Card>
          <EmptyState
            icon={<FileText className="h-12 w-12 text-secondary-300" aria-hidden="true" />}
            title="No notes yet"
            description={readOnly ? 'This project has no notes.' : 'Add meeting minutes, site observations or decisions. Notes support headings, bold, italic, lists and links.'}
            action={!readOnly ? <Button size="sm" onClick={() => setView({ kind: 'new' })}>+ Add Note</Button> : undefined}
          />
        </Card>
      ) : (
        <ul className="space-y-3" aria-label="Project notes">
          {notes.map((note) => (
            <li key={note.id}>
              <div className="flex items-start gap-3 rounded-lg border border-secondary-200/60 bg-white p-4 shadow-sm transition-colors hover:border-secondary-300">
                <button
                  type="button"
                  onClick={() => setView({ kind: 'view', noteId: note.id })}
                  className="min-w-0 flex-1 text-left"
                >
                  <p className="truncate text-sm font-semibold text-secondary-900">{note.title}</p>
                  <p className="mt-0.5 text-xs text-secondary-500">{noteMeta(note)}</p>
                  {note.content_text && (
                    <p className="mt-2 line-clamp-2 text-sm text-secondary-600">{note.content_text}</p>
                  )}
                </button>
                {note.can_edit && !readOnly && (
                  <DropdownMenu
                    trigger={<IconButton icon={<MoreHorizontal className="h-4 w-4" />} aria-label={`Actions for ${note.title}`} variant="ghost" size="sm" />}
                    align="right"
                  >
                    <DropdownMenuItem icon={<Pencil className="h-4 w-4" />} onClick={() => setView({ kind: 'edit', noteId: note.id })}>
                      Edit
                    </DropdownMenuItem>
                    <DropdownMenuItem icon={<Trash2 className="h-4 w-4" />} destructive onClick={() => setDeleteTarget(note)}>
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenu>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {deleteDialog}
    </div>
  );
}
