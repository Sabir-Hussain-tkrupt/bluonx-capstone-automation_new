import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchBidTemplateById } from '@/features/bid-templates/api/bid-template.queries';

export function useBidTemplate(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.bidTemplates.detail(id!),
    queryFn: () => fetchBidTemplateById(id!),
    enabled: !!id,
  });
}
