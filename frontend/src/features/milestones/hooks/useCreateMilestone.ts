import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createMilestone } from '@/features/milestones/api/milestone.mutations';
import type { CreateMilestoneInput } from '@/features/milestones/api/milestone.mutations';

export function useCreateMilestone() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateMilestoneInput) => createMilestone(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.milestones.lists() });
    },
  });
}
