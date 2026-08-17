import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  ContractSigner,
  ContractSignerCreateRequest,
  ContractSignerUpdateRequest,
} from '../types';

/**
 * POST /contract-signers — add someone to the roster.
 *
 * The backend returns a 409 whose `detail` distinguishes a live duplicate from a
 * previously deactivated entry the admin should reactivate instead. Both are
 * surfaced verbatim.
 */
export async function createContractSigner(
  body: ContractSignerCreateRequest,
): Promise<ContractSigner> {
  const { data } = await api.post(API_ENDPOINTS.CONTRACT_SIGNERS, body);
  return data as ContractSigner;
}

/**
 * PATCH /contract-signers/{id} — edit details, or activate/deactivate.
 *
 * Deactivating the last active signer returns a 409 we surface verbatim; the
 * client cannot know the live active count, so that guard is not mirrored here.
 */
export async function updateContractSigner(
  id: string,
  patch: ContractSignerUpdateRequest,
): Promise<ContractSigner> {
  const { data } = await api.patch(API_ENDPOINTS.CONTRACT_SIGNER(id), patch);
  return data as ContractSigner;
}
