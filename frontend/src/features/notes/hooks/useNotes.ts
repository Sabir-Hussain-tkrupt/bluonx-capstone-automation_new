import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createNote, deleteNote, fetchNotes, updateNote, type NoteInput } from '../api/note.api';

export function useNotes(projectId: string) {
  return useQuery({
    queryKey: queryKeys.notes.project(projectId),
    queryFn: () => fetchNotes(projectId),
    enabled: !!projectId,
  });
}

function useInvalidate(projectId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: queryKeys.notes.project(projectId) });
}

export function useCreateNote(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({ mutationFn: (input: NoteInput) => createNote(projectId, input), onSuccess: invalidate });
}

export function useUpdateNote(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: ({ noteId, input }: { noteId: string; input: Partial<NoteInput> }) => updateNote(noteId, input),
    onSuccess: invalidate,
  });
}

export function useDeleteNote(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({ mutationFn: (noteId: string) => deleteNote(noteId), onSuccess: invalidate });
}
