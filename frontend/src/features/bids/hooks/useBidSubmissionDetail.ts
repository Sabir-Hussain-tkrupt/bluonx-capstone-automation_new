import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchBidSubmissionDetail } from '@/features/bids/api/bid-package.queries';

export function useBidSubmissionDetail(submissionId: string | null) {
  return useQuery({
    queryKey: queryKeys.bidSubmissions.detail(submissionId ?? ''),
    queryFn: () => fetchBidSubmissionDetail(submissionId as string),
    enabled: !!submissionId,
  });
}
