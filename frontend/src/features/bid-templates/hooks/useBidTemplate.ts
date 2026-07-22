import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import type { ApiError } from '@/lib/api';
import { fetchBidTemplateById } from '@/features/bid-templates/api/bid-template.queries';
import type { BidTemplateDetail } from '@/features/bid-templates/api/bid-template.queries';

// The error generic is declared so callers can branch on `error.status`
// without casting. The api interceptor rejects with ApiError, but React
// Query's default error type is Error, and casting between the two is exactly
// what the pre-existing tsc -b failures on the vendor pages are.
export function useBidTemplate(id: string | undefined) {
  return useQuery<BidTemplateDetail, ApiError>({
    queryKey: queryKeys.bidTemplates.detail(id!),
    queryFn: () => fetchBidTemplateById(id!),
    enabled: !!id,
  });
}
