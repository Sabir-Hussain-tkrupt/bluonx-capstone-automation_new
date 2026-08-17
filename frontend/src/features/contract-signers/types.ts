/**
 * Types for the admin Contract Signers feature.
 *
 * Mirrors the backend Pydantic models (backend/app/models/contract_signers.py).
 * Reads come straight from Supabase: `contract_signers_select_authenticated`
 * lets any active user read every row, inactive ones included, so the roster
 * needs no server-computed fields. Writes go through FastAPI, which is where the
 * last-signer and reactivation guards live.
 */

/** A row in public.contract_signers. */
export interface ContractSigner {
  id: string;
  full_name: string;
  email: string;
  title: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** POST /contract-signers body. */
export interface ContractSignerCreateRequest {
  full_name: string;
  email: string;
  title?: string | null;
}

/** PATCH /contract-signers/{id} body — every field is independently optional. */
export interface ContractSignerUpdateRequest {
  full_name?: string;
  email?: string;
  title?: string | null;
  is_active?: boolean;
}
