import { useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchBidSubmissionDetail } from '@/features/bids/api/bid-package.queries';
import type { BidSubmissionDetail } from '@/features/bids/types';

const MAX_HOPS = 5; // safety cap; product cap is 2 revisions (3 versions)

/**
 * Builds a vendor's full submission version history by walking
 * `supersedes_submission_id` backwards from the current submission via
 * GET /bid-submissions/{id}. Each hop is cached under
 * queryKeys.bidSubmissions.detail(id) so it is shared with the
 * View-Full-Bid modal (instant re-open).
 *
 * Returns versions sorted ascending by revision_number (v1 first).
 * `enabled` should be true only when the vendor row is expanded.
 */
export function useVendorVersionHistory(
  currentSubmissionId: string | null,
  enabled: boolean,
) {
  const queryClient = useQueryClient();

  return useQuery({
    queryKey: [
      ...queryKeys.bidSubmissions.all,
      'version-history',
      currentSubmissionId ?? '',
    ],
    enabled: enabled && !!currentSubmissionId,
    queryFn: async (): Promise<BidSubmissionDetail[]> => {
      const versions: BidSubmissionDetail[] = [];
      let nextId: string | null = currentSubmissionId;
      let hops = 0;

      while (nextId && hops < MAX_HOPS) {
        const submission: BidSubmissionDetail =
          await queryClient.fetchQuery({
            queryKey: queryKeys.bidSubmissions.detail(nextId),
            queryFn: () => fetchBidSubmissionDetail(nextId as string),
          });
        versions.push(submission);
        nextId = submission.supersedes_submission_id;
        hops += 1;
      }

      return versions.sort((a, b) => a.revision_number - b.revision_number);
    },
  });
}
