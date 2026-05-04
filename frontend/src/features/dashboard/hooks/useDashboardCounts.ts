import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  fetchOpenTaskCount,
  fetchPendingBidCount,
} from '@/features/dashboard/api/dashboard.queries';

export interface DashboardCounts {
  openTaskCount: number | undefined;
  pendingBidCount: number | undefined;
  isLoading: boolean;
}

export function useDashboardCounts(): DashboardCounts {
  const { data: openTaskCount, isLoading: loadingTasks } = useQuery({
    queryKey: queryKeys.dashboard.openTaskCount(),
    queryFn: () => fetchOpenTaskCount(),
  });

  const { data: pendingBidCount, isLoading: loadingBids } = useQuery({
    queryKey: queryKeys.dashboard.pendingBidCount(),
    queryFn: () => fetchPendingBidCount(),
  });

  return {
    openTaskCount,
    pendingBidCount,
    isLoading: loadingTasks || loadingBids,
  };
}
