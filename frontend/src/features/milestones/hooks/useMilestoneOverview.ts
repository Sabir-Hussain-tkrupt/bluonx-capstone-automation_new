import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  fetchMilestoneOverview,
  type MilestoneOverviewFilters,
} from '@/features/milestones/api/milestoneOverview.queries';

/** Cross-project milestone list (filter / sort / paginate) for `/milestones`. */
export function useMilestoneOverview(filters?: MilestoneOverviewFilters) {
  return useQuery({
    queryKey: queryKeys.milestones.overview(filters as Record<string, unknown>),
    queryFn: () => fetchMilestoneOverview(filters),
  });
}
