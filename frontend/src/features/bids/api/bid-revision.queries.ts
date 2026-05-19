import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { BidRevisionRequest } from '@/features/bids/types';

/**
 * All revision requests for a bid package, newest first
 * (backend sorts by requested_at DESC).
 */
export async function fetchRevisionRequests(
  bidPackageId: string,
): Promise<BidRevisionRequest[]> {
  const { data } = await api.get<BidRevisionRequest[]>(
    API_ENDPOINTS.BID_REVISION_REQUESTS,
    { params: { bid_package_id: bidPackageId } },
  );
  return data;
}
