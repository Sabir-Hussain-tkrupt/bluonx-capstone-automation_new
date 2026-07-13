import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { rescheduleMilestone } from '@/features/milestones/api/milestone.mutations';

interface RescheduleArgs {
  id: string;
  endDate: string;
}

export function useRescheduleMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, endDate }: RescheduleArgs) => rescheduleMilestone(id, endDate),
    onSuccess: (milestone) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.lists() });
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.detail(milestone.id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.events(milestone.id) });
    },
  });
}
