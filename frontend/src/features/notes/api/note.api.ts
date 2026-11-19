import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';

/**
 * Project notes — rich-text, document-sized. Everything goes through FastAPI,
 * which adds author names and whether the current user may edit each note.
 */

export interface ProjectNote {
  id: string;
  project_id: string;
  title: string;
  /** HTML produced by the editor; rendered back through the editor, never as raw HTML. */
  content_html: string;
  /** Plain-text copy for previews. */
  content_text: string;
  created_by: string;
  created_by_name: string | null;
  updated_by: string | null;
  updated_by_name: string | null;
  created_at: string;
  updated_at: string;
  can_edit: boolean;
}

export interface NoteInput {
  title: string;
  content_html: string;
  content_text: string;
}

export async function fetchNotes(projectId: string): Promise<ProjectNote[]> {
  const { data } = await api.get<ProjectNote[]>(API_ENDPOINTS.PROJECT_NOTES(projectId));
  return data ?? [];
}

export async function createNote(projectId: string, input: NoteInput): Promise<ProjectNote> {
  const { data } = await api.post<ProjectNote>(API_ENDPOINTS.PROJECT_NOTES(projectId), input);
  return data;
}

export async function updateNote(noteId: string, input: Partial<NoteInput>): Promise<ProjectNote> {
  const { data } = await api.patch<ProjectNote>(API_ENDPOINTS.PROJECT_NOTE(noteId), input);
  return data;
}

export async function deleteNote(noteId: string): Promise<void> {
  await api.delete(API_ENDPOINTS.PROJECT_NOTE(noteId));
}
