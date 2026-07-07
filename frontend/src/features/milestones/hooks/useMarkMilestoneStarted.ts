import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { markMilestoneStarted } from '@/features/milestones/api/milestone.mutations';

interface MarkStartedArgs {
  id: string;
  actualStartDate?: string | null;
}

export function useMarkMilestoneStarted() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, actualStartDate }: MarkStartedArgs) =>
      markMilestoneStarted(id, actualStartDate),
    onSuccess: (milestone) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.detail(milestone.id) });
    },
  });
}
