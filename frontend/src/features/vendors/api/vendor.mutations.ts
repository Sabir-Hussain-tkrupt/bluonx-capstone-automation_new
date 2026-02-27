import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { Vendor } from '@/features/vendors/api/vendor.queries';

// ─── Mutation Input Types ─────────────────────────────────────────────

export interface CreateVendorInput {
  company_name: string;
  entity_type: string;
  address_line1: string;
  city: string;
  state: string;
  zip_code: string;
  dba_name?: string;
  phone?: string;
  email?: string;
  website?: string;
  notes?: string;
}

export interface UpdateVendorInput {
  id: string;
  company_name?: string;
  phone?: string;
  email?: string;
  website?: string;
  notes?: string;
  vendor_status?: string;
}

// ─── FastAPI Write Operations ─────────────────────────────────────────
// NOTE: FastAPI backend is not built yet (Task 2.6).
// These functions establish the pattern for all write operations.

/**
 * Create a new vendor via FastAPI.
 * FastAPI validates, writes with service_role, returns the created vendor.
 */
export async function createVendor(input: CreateVendorInput): Promise<Vendor> {
  const { data } = await api.post<Vendor>(API_ENDPOINTS.VENDORS, input);
  return data;
}

/**
 * Update an existing vendor via FastAPI.
 */
export async function updateVendor({ id, ...input }: UpdateVendorInput): Promise<Vendor> {
  const { data } = await api.patch<Vendor>(API_ENDPOINTS.VENDOR(id), input);
  return data;
}

/**
 * Soft-delete a vendor via FastAPI (sets deleted_at timestamp).
 */
export async function deleteVendor(id: string): Promise<void> {
  await api.delete(API_ENDPOINTS.VENDOR(id));
}
