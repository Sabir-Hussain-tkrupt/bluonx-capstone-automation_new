import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import { API_ENDPOINTS } from '@/constants/api';
import type { EscrowDetail, Jurisdiction, LongTailOverview } from '../types';

export function useLongTail(projectId: string) {
  return useQuery({
    queryKey: queryKeys.longTail.project(projectId),
    queryFn: async () => (await api.get<LongTailOverview>(API_ENDPOINTS.PROJECT_LONG_TAIL(projectId))).data,
    enabled: !!projectId,
  });
}

export function useEscrow(id: string) {
  return useQuery({
    queryKey: queryKeys.longTail.escrow(id),
    queryFn: async () => (await api.get<EscrowDetail>(API_ENDPOINTS.ESCROW(id))).data,
    enabled: !!id,
  });
}

export function useJurisdictions() {
  return useQuery({
    queryKey: queryKeys.longTail.jurisdictions(),
    queryFn: async () => (await api.get<Jurisdiction[]>(API_ENDPOINTS.JURISDICTIONS)).data,
  });
}

/** Long-tail lines move the budget and contingency: refresh them too. */
function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.longTail.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.budgets.all });
  };
}

/** One mutation for every long-tail write: method + url + body. */
export function useLongTailWrite() {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async ({ method, url, body }: { method: 'post' | 'put' | 'patch'; url: string; body?: unknown }) =>
      (await api[method](url, body)).data,
    onSuccess,
  });
}

export function useUploadEscrowDocument(escrowId: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append('file', file);
      return (await api.post(API_ENDPOINTS.ESCROW_DOCUMENT(escrowId), form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120_000,
      })).data;
    },
    onSuccess,
  });
}

export async function openEscrowDocument(escrowId: string) {
  const { data } = await api.get<{ url: string }>(API_ENDPOINTS.ESCROW_DOCUMENT(escrowId));
  window.open(data.url, '_blank', 'noopener');
}
