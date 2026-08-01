import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchVendorEmailLog } from '@/features/vendors/api/vendor.queries';

export const EMAIL_LOG_PAGE_SIZE = 25;

export function useVendorEmailLog(vendorId: string, enabled = true, page = 1) {
  return useQuery({
    queryKey: queryKeys.vendors.emailLog(vendorId, page, EMAIL_LOG_PAGE_SIZE),
    queryFn: () =>
      fetchVendorEmailLog(vendorId, { page, pageSize: EMAIL_LOG_PAGE_SIZE }),
    enabled: !!vendorId && enabled,
    // Hold the previous page while the next one loads, so paging does not
    // collapse the table to a skeleton and jump the layout.
    placeholderData: (prev) => prev,
  });
}
