import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { duplicateBidTemplate } from '@/features/bid-templates/api/bid-template.mutations';

export function useDuplicateBidTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => duplicateBidTemplate(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bidTemplates.lists() });
    },
  });
}
