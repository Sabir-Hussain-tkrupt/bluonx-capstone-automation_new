import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  CreateBidPackageRequest,
  CreateBidPackageResponse,
  ResendBidLinkResponse,
  UpdateInvitationStatusRequest,
} from '@/features/bids/types';

export async function createBidPackage(
  taskId: string,
  input: CreateBidPackageRequest,
): Promise<CreateBidPackageResponse> {
  const { data } = await api.post<CreateBidPackageResponse>(
    API_ENDPOINTS.TASK_BID_PACKAGES(taskId),
    input,
  );
  return data;
}

/**
 * Manually close bidding early (open -> evaluating). Allowed only from 'open';
 * the backend returns 409 otherwise. Stops new bid inflow immediately.
 */
export async function closeBidding(
  bidPackageId: string,
): Promise<{ id: string; status: string }> {
  const { data } = await api.post<{ id: string; status: string }>(
    API_ENDPOINTS.BID_PACKAGE_CLOSE(bidPackageId),
  );
  return data;
}

/**
 * Void a bidding round (open | evaluating -> cancelled). Submitted bids are
 * kept as history but stop being awardable, and any pending revision requests
 * are cancelled server-side. 409 from any other status, or when the task has
 * already been awarded.
 */
export async function cancelBidPackage(bidPackageId: string): Promise<{
  id: string;
  status: string;
  no_response_count: number;
  revisions_cancelled: number;
}> {
  const { data } = await api.post<{
    id: string;
    status: string;
    no_response_count: number;
    revisions_cancelled: number;
  }>(API_ENDPOINTS.BID_PACKAGE_CANCEL(bidPackageId));
  return data;
}

export async function resendBidLink(invitationId: string): Promise<ResendBidLinkResponse> {
  const { data } = await api.post<ResendBidLinkResponse>(
    API_ENDPOINTS.BID_INVITATION_RESEND_LINK(invitationId),
  );
  return data;
}

export async function updateInvitationStatus(
  invitationId: string,
  input: UpdateInvitationStatusRequest,
): Promise<unknown> {
  const { data } = await api.put(API_ENDPOINTS.BID_INVITATION_STATUS(invitationId), input);
  return data;
}
