import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchContractReview } from '@/features/contracts/api/review.queries';

/** The existing review for a contract (or null). */
export function useContractReview(contractId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.reviews.forContract(contractId ?? ''),
    queryFn: () => fetchContractReview(contractId!),
    enabled: !!contractId,
  });
}
