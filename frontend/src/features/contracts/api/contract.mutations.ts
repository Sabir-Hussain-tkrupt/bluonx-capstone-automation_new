import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { TaskActiveContract } from '@/features/milestones/api/milestone.queries';
import type { VendorPerformanceReview } from './review.queries';

// ─── Mutation Input Types ─────────────────────────────────────────────

export interface ReviewInput {
  rating: number;
  notes?: string | null;
}

// ─── FastAPI Write Operations ─────────────────────────────────────────

/** Mark a contract's work complete (gated server-side by fn_mark_contract_complete). */
export async function markContractComplete(contractId: string): Promise<TaskActiveContract> {
  const { data } = await api.post<TaskActiveContract>(
    API_ENDPOINTS.CONTRACT_MARK_COMPLETE(contractId),
  );
  return data;
}

/** Create the one vendor performance review for a completed contract. */
export async function createReview(
  contractId: string,
  input: ReviewInput,
): Promise<VendorPerformanceReview> {
  const { data } = await api.post<VendorPerformanceReview>(
    API_ENDPOINTS.CONTRACT_REVIEW(contractId),
    { rating: input.rating, notes: input.notes ?? null },
  );
  return data;
}

/** Correct an existing review's rating / notes. */
export async function updateReview(
  reviewId: string,
  input: ReviewInput,
): Promise<VendorPerformanceReview> {
  const { data } = await api.patch<VendorPerformanceReview>(API_ENDPOINTS.REVIEW(reviewId), {
    rating: input.rating,
    notes: input.notes ?? null,
  });
  return data;
}
