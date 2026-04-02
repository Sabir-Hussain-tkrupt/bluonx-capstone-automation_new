import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchBidTemplates } from '@/features/bid-templates/api/bid-template.queries';
import type { BidTemplateListFilters } from '@/features/bid-templates/api/bid-template.queries';

export function useBidTemplates(filters?: BidTemplateListFilters) {
  return useQuery({
    queryKey: queryKeys.bidTemplates.list(filters as Record<string, unknown>),
    queryFn: () => fetchBidTemplates(filters),
  });
}
