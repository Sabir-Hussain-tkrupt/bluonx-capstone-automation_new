import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  CreateBidPackageRequest,
  CreateBidPackageResponse,
  ResendInvitationResponse,
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

export async function resendInvitation(invitationId: string): Promise<ResendInvitationResponse> {
  const { data } = await api.post<ResendInvitationResponse>(
    API_ENDPOINTS.BID_INVITATION_RESEND(invitationId),
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
