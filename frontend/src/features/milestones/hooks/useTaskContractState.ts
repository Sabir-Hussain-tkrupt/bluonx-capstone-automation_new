import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchTaskAwardState } from '@/features/milestones/api/milestone.queries';

/**
 * The task's active award, its contract, and whether the DocuSign envelope
 * actually went out — one read, so no surface has to derive this from three.
 *
 * Keyed under `contracts.list` deliberately: `useMarkContractComplete`
 * invalidates `contracts.lists()`, and that invalidation must keep reaching this
 * query after the read was re-keyed from contracts to awards.
 */
export function useTaskContractState(taskId: string) {
  return useQuery({
    queryKey: queryKeys.contracts.list({ taskId }),
    queryFn: () => fetchTaskAwardState(taskId),
    enabled: !!taskId,
  });
}
