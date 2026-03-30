import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { queryKeys } from '@/lib/queryKeys';
import {
  uploadProjectDocument,
  deleteProjectDocument,
  getProjectDocumentUrl,
} from '@/features/projects/api/project-documents.mutations';

/** Fetch project documents directly from Supabase (read pattern). */
async function fetchProjectDocuments(projectId: string) {
  const { data, error } = await supabase
    .from('project_documents')
    .select('*')
    .eq('project_id', projectId)
    .order('uploaded_at', { ascending: false });

  if (error) throw error;
  return data ?? [];
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
      queryClient.invalidateQueries({
        queryKey: [...queryKeys.projects.detail(variables.projectId), 'documents'],
      });
    },
  });
}

export function useDeleteProjectDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ projectId, docId }: { projectId: string; docId: string }) =>
      deleteProjectDocument(projectId, docId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: [...queryKeys.projects.detail(variables.projectId), 'documents'],
      });
    },
  });
}

export function useProjectDocumentDownload() {
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const download = async (projectId: string, docId: string) => {
    setDownloadingId(docId);
    try {
      const url = await getProjectDocumentUrl(projectId, docId);
      window.open(url, '_blank');
    } finally {
      setDownloadingId(null);
    }
  };

  return { download, downloadingId };
}
