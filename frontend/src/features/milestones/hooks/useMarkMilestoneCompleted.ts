import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { markMilestoneCompleted } from '@/features/milestones/api/milestone.mutations';

interface MarkCompletedArgs {
  id: string;
  actualEndDate?: string | null;
}

export function useMarkMilestoneCompleted() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, actualEndDate }: MarkCompletedArgs) =>
      markMilestoneCompleted(id, actualEndDate),
    onSuccess: (milestone) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.detail(milestone.id) });
    },
  });
}
