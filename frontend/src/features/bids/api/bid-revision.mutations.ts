import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  BidRevisionRequest,
  CreateRevisionRequestPayload,
  CreateRevisionRequestResponse,
} from '@/features/bids/types';

export async function createRevisionRequest(
  payload: CreateRevisionRequestPayload,
): Promise<CreateRevisionRequestResponse> {
  const { data } = await api.post<CreateRevisionRequestResponse>(
    API_ENDPOINTS.BID_REVISION_REQUESTS,
    payload,
  );
  return data;
}

/** Cancel a still-pending revision request. POST, not DELETE. */
export async function cancelRevisionRequest(
  revisionRequestId: string,
): Promise<BidRevisionRequest> {
  const { data } = await api.post<BidRevisionRequest>(
    API_ENDPOINTS.BID_REVISION_REQUEST_CANCEL(revisionRequestId),
  );
  return data;
}
