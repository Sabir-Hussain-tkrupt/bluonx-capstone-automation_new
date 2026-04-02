import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createBidTemplate } from '@/features/bid-templates/api/bid-template.mutations';
import type { CreateBidTemplateInput } from '@/features/bid-templates/api/bid-template.mutations';

export function useCreateBidTemplate() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateBidTemplateInput) => createBidTemplate(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.bidTemplates.lists() });
    },
  });
}
