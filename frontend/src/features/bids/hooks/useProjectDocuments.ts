import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchProjectDocuments } from '@/features/bids/api/bid-package.queries';

export function useProjectDocuments(projectId: string) {
  return useQuery({
    queryKey: queryKeys.projectDocuments.all(projectId),
    queryFn: () => fetchProjectDocuments(projectId),
    enabled: !!projectId,
  });
}
