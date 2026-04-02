import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { updateBidTemplate } from '@/features/bid-templates/api/bid-template.mutations';
import type { UpdateBidTemplateInput } from '@/features/bid-templates/api/bid-template.mutations';

export function useUpdateBidTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateBidTemplateInput) => updateBidTemplate(input),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bidTemplates.lists() });
      queryClient.invalidateQueries({
        queryKey: queryKeys.bidTemplates.detail(variables.id),
      });
    },
  });
}
