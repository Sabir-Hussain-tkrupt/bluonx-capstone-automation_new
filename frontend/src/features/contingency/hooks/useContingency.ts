import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  cancelTopUp,
  completeBidding,
  decideTopUp,
  fetchBiddingCheckpoint,
  fetchContingency,
  fetchContingencyLedger,
  fetchContingencySettings,
  reopenBidding,
  requestTopUp,
  setContingencyPercent,
  updateContingencySettings,
} from '../api/contingency.api';
import type { ContingencySettings } from '../types';

// ─── Reads ────────────────────────────────────────────────────────────

export function useContingency(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.budgets.contingency(projectId),
    queryFn: () => fetchContingency(projectId),
    enabled: !!projectId && enabled,
  });
}

export function useContingencyLedger(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.budgets.contingencyLedger(projectId),
    queryFn: () => fetchContingencyLedger(projectId),
    enabled: !!projectId && enabled,
  });
}

export function useBiddingCheckpoint(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.budgets.biddingCheckpoint(projectId),
    queryFn: () => fetchBiddingCheckpoint(projectId),
    enabled: !!projectId && enabled,
    staleTime: 0,
  });
}

export function useContingencySettings() {
  return useQuery({ queryKey: queryKeys.contingencySettings, queryFn: fetchContingencySettings });
}

// ─── Writes ───────────────────────────────────────────────────────────

/** Contingency moves budget totals too: refresh the whole project budget. */
function useInvalidate(projectId: string) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.budgets.project(projectId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.projects.detail(projectId) });
  };
}

export function useSetContingencyPercent(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: (percent: string | null) => setContingencyPercent(projectId, percent),
    onSuccess: invalidate,
  });
}

export function useRequestTopUp(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: (body: { amount: string; reason: string }) => requestTopUp(projectId, body),
    onSuccess: invalidate,
  });
}

export function useDecideTopUp(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: ({ bucketId, body }: { bucketId: string; body: { approve: boolean; approved_amount?: string | null; note?: string | null } }) =>
      decideTopUp(bucketId, body),
    onSuccess: invalidate,
  });
}

export function useCancelTopUp(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({ mutationFn: (bucketId: string) => cancelTopUp(bucketId), onSuccess: invalidate });
}

export function useCompleteBidding(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: (body: { note?: string | null; acknowledge_open_tasks: boolean }) => completeBidding(projectId, body),
    onSuccess: invalidate,
  });
}

export function useReopenBidding(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({ mutationFn: () => reopenBidding(projectId), onSuccess: invalidate });
}

export function useUpdateContingencySettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Record<keyof ContingencySettings, string | string[]>>) => updateContingencySettings(body),
    onSuccess: (data) => queryClient.setQueryData(queryKeys.contingencySettings, data),
  });
}
