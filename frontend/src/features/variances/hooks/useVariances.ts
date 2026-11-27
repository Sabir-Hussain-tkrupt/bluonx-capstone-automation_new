import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import { API_ENDPOINTS } from '@/constants/api';
import type { Variance, VarianceDetail, VarianceInput } from '../types';

export function useVariances(projectId?: string) {
  const filters = projectId ? { project_id: projectId } : {};
  return useQuery({
    queryKey: queryKeys.variances.list(filters),
    queryFn: async () => (await api.get<Variance[]>(API_ENDPOINTS.VARIANCES, { params: filters })).data,
  });
}

export function useVariance(id: string) {
  return useQuery({
    queryKey: queryKeys.variances.detail(id),
    queryFn: async () => (await api.get<VarianceDetail>(API_ENDPOINTS.VARIANCE(id))).data,
  });
}

/** A variance moves contingency and budget totals too: refresh them all. */
function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.variances.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.budgets.all });
  };
}

export function useCreateVariance(lineId: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async (body: VarianceInput) =>
      (await api.post<Variance>(API_ENDPOINTS.BUDGET_LINE_VARIANCES(lineId), body)).data,
    onSuccess,
  });
}

export function useUpdateVariance(id: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async (body: VarianceInput) => (await api.patch<Variance>(API_ENDPOINTS.VARIANCE(id), body)).data,
    onSuccess,
  });
}

export function useCancelVariance(id: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async (note: string | null) =>
      (await api.post<Variance>(API_ENDPOINTS.VARIANCE_CANCEL(id), { note })).data,
    onSuccess,
  });
}

export function useApproveVariance(id: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async ({ note, confirm }: { note: string | null; confirm: boolean }) =>
      (await api.post<Variance>(API_ENDPOINTS.VARIANCE_APPROVE(id), { note, confirm_work_complete: confirm })).data,
    onSuccess,
  });
}

export function useRejectVariance(id: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async (reason: string) =>
      (await api.post<Variance>(API_ENDPOINTS.VARIANCE_REJECT(id), { reason })).data,
    onSuccess,
  });
}
