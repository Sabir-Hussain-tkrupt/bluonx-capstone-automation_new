import { api } from '@/lib/api';

export async function uploadProjectDocument(projectId: string, formData: FormData) {
  const { data } = await api.post(`/projects/${projectId}/documents`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000, // 2 min for large files
  });
  return data;
}

export async function deleteProjectDocument(projectId: string, docId: string) {
  await api.delete(`/projects/${projectId}/documents/${docId}`);
}

export async function getProjectDocumentUrl(projectId: string, docId: string): Promise<string> {
  const { data } = await api.get<{ url: string }>(`/projects/${projectId}/documents/${docId}/url`);
  return data.url;
}
