import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { queryKeys } from '@/lib/queryKeys';
import { useToast } from '@/components/ui/Toast/useToast';
import { errorMessage } from '@/lib/api';
import {
  uploadProjectDocument,
  deleteProjectDocument,
  getProjectDocumentUrl,
} from '@/features/projects/api/project-documents.mutations';
import type { DocumentItem } from '@/components/ui/DocumentList/DocumentList';

/**
 * Project documents are read two ways: this hook keys them under
 * `projects.detail(id)` while the bid wizard's scope-of-work picker keys them
 * under `projectDocuments.all(id)`. Invalidate both after a write so neither
 * view goes stale.
 */
function projectDocumentKeys(projectId: string) {
  return [
    [...queryKeys.projects.detail(projectId), 'documents'] as const,
    queryKeys.projectDocuments.all(projectId),
  ];
}

/** Fetch project documents directly from Supabase (read pattern). */
async function fetchProjectDocuments(projectId: string) {
  const { data, error } = await supabase
    .from('project_documents')
    .select('*')
    .eq('project_id', projectId)
    .order('uploaded_at', { ascending: false });

  if (error) throw error;
  return (data ?? []) as unknown as DocumentItem[];
}

export function useProjectDocumentsList(projectId: string) {
  return useQuery({
    queryKey: [...queryKeys.projects.detail(projectId), 'documents'],
    queryFn: () => fetchProjectDocuments(projectId),
    enabled: !!projectId,
  });
}

export function useUploadProjectDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, formData }: { projectId: string; formData: FormData }) =>
      uploadProjectDocument(projectId, formData),
    onSuccess: (_data, variables) => {
      for (const queryKey of projectDocumentKeys(variables.projectId)) {
        queryClient.invalidateQueries({ queryKey });
      }
    },
  });
}

export function useDeleteProjectDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, docId }: { projectId: string; docId: string }) =>
      deleteProjectDocument(projectId, docId),
    onSuccess: (_data, variables) => {
      for (const queryKey of projectDocumentKeys(variables.projectId)) {
        queryClient.invalidateQueries({ queryKey });
      }
    },
  });
}

export function useProjectDocumentDownload() {
  const { toast } = useToast();
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const download = async (projectId: string, docId: string) => {
    setDownloadingId(docId);
    try {
      const url = await getProjectDocumentUrl(projectId, docId);

      // An anchor click keeps this within the user's original gesture.
      // window.open() after an await is treated as programmatic by Chrome and
      // Safari and gets caught by the popup blocker, which looked to the user
      // like the download silently doing nothing.
      const link = document.createElement('a');
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      // Previously try/finally with no catch: a failed signed-URL request
      // cleared the spinner and told the user nothing at all.
      toast({ variant: 'danger', message: errorMessage(error, 'Could not download the document.') });
    } finally {
      setDownloadingId(null);
    }
  };

  return { download, downloadingId };
}
