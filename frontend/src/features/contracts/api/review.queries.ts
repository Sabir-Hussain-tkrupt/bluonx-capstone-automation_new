import { supabase } from '@/lib/supabase';
import type { ApiError } from '@/lib/api';

/** One row of vendor_performance_reviews — the single review for a contract. */
export interface VendorPerformanceReview {
  id: string;
  contract_id: string;
  vendor_id: string;
  rating: number;
  notes: string | null;
  reviewed_by: string | null;
  reviewed_at: string;
  created_at: string;
  updated_at: string;
}

function toApiError(error: { message: string; code?: string }): ApiError {
  return {
    message: error.message,
    code: error.code ?? 'SUPABASE_ERROR',
    status: 0,
    details: error,
  };
}

/**
 * The one review for a contract, or null. Read direct via Supabase under RLS
 * (writes go through FastAPI). UNIQUE(contract_id) guarantees at most one row.
 */
export async function fetchContractReview(
  contractId: string,
): Promise<VendorPerformanceReview | null> {
  const { data, error } = await supabase
    .from('vendor_performance_reviews')
    .select('*')
    .eq('contract_id', contractId)
    .maybeSingle();

  if (error) throw toApiError(error);
  return (data as unknown as VendorPerformanceReview | null) ?? null;
}
