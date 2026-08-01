import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchBidPackageEmailLog } from '@/features/bids/api/bid-package.queries';

export const EMAIL_LOG_PAGE_SIZE = 25;

export function useBidPackageEmailLog(
  bidPackageId: string,
  enabled = true,
  page = 1,
) {
  return useQuery({
    queryKey: queryKeys.bidInvitations.emailLog(
      bidPackageId,
      page,
      EMAIL_LOG_PAGE_SIZE,
    ),
    queryFn: () =>
      fetchBidPackageEmailLog(bidPackageId, {
        page,
        pageSize: EMAIL_LOG_PAGE_SIZE,
      }),
    enabled: !!bidPackageId && enabled,
    // Hold the previous page while the next one loads, so paging does not
    // collapse the table to a skeleton and jump the layout.
    placeholderData: (prev) => prev,
  });
}
