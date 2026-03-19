import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchActiveTrades } from '@/features/tasks/api/task.queries';

export function useTrades() {
  return useQuery({
    queryKey: queryKeys.trades.lists(),
    queryFn: fetchActiveTrades,
  });
}
