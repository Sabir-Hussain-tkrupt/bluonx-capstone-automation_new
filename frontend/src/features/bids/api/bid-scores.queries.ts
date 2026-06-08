import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { BidScoreCohort } from '@/features/bids/types';

export async function fetchBidPackageScores(
  bidPackageId: string,
): Promise<BidScoreCohort> {
  const { data } = await api.get<BidScoreCohort>(
    API_ENDPOINTS.BID_PACKAGE_SCORES(bidPackageId),
  );
  return data;
}

export async function computeBidPackageScores(
  bidPackageId: string,
): Promise<BidScoreCohort> {
  const { data } = await api.post<BidScoreCohort>(
    API_ENDPOINTS.BID_PACKAGE_SCORES(bidPackageId),
  );
  return data;
}
