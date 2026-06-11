import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { Award, CreateAwardPayload } from '@/features/bids/types';

/**
 * Create an award for a bid submission (Task 9.2). The server recomputes the
 * pre-award validation and gates the write; a `warn` requires has_override +
 * justification, a `block` is rejected (422). Returns the written award row.
 */
export async function createAward(payload: CreateAwardPayload): Promise<Award> {
  const { data } = await api.post<Award>(API_ENDPOINTS.AWARDS, payload);
  return data;
}
