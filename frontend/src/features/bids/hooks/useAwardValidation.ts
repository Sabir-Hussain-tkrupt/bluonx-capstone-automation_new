import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchAwardValidation } from '@/features/bids/api/award.queries';

/**
 * Lazy pre-award validation preview for a candidate submission. `enabled` is
 * driven by whether a submission id is present (i.e. the award dialog is open),
 * so the preview is only fetched when the PM clicks Award.
 */
export function useAwardValidation(bidSubmissionId: string | null) {
  return useQuery({
    queryKey: queryKeys.awards.validation(bidSubmissionId ?? ''),
    queryFn: () => fetchAwardValidation(bidSubmissionId as string),
    enabled: !!bidSubmissionId,
    // Validation reflects live vendor/package data — don't serve it stale.
    staleTime: 0,
  });
}
