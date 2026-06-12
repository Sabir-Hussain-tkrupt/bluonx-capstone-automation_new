import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { PreAwardValidationResult } from '@/features/bids/types';

/**
 * Read-only pre-award validation preview (Task 9.1). No side effects — a
 * blocking result still returns 200 with the block detail so the override
 * dialog can render *why* awarding is blocked.
 */
export async function fetchAwardValidation(
  bidSubmissionId: string,
): Promise<PreAwardValidationResult> {
  const { data } = await api.get<PreAwardValidationResult>(
    API_ENDPOINTS.AWARD_VALIDATE(bidSubmissionId),
  );
  return data;
}
