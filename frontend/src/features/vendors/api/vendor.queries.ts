import { supabase } from '@/lib/supabase';
import type { ApiError } from '@/lib/api';

// ─── Types ────────────────────────────────────────────────────────────
/**
 * Vendor row shape.
 *
 * Temporary type until database.types.ts is fully generated via
 * `npx supabase gen types typescript`. Once generated, replace with:
 *   import type { Database } from '@/types/database.types';
 *   type Vendor = Database['public']['Tables']['vendors']['Row'];
 */
export interface Vendor {
  id: string;
  company_name: string;
  dba_name: string | null;
  entity_type: string;
  ein_last_four: string | null;
  address_line1: string;
  address_line2: string | null;
  city: string;
  state: string;
  zip_code: string;
  phone: string | null;
  email: string | null;
  website: string | null;
  vendor_status: string;
  rating: number | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface VendorListFilters {
  status?: string;
  search?: string;
}

// ─── Supabase Direct Reads ────────────────────────────────────────────

/**
 * Fetch all vendors. RLS ensures only authenticated users see data.
 */
export async function fetchVendors(filters?: VendorListFilters): Promise<Vendor[]> {
  let query = supabase
    .from('vendors')
    .select('*')
    .is('deleted_at', null)
    .order('company_name', { ascending: true });

  if (filters?.status) {
    query = query.eq('vendor_status', filters.status);
  }

  if (filters?.search) {
    query = query.ilike('company_name', `%${filters.search}%`);
  }

  const { data, error } = await query;

  if (error) {
    const apiError: ApiError = {
      message: error.message,
      code: error.code,
      status: 0,
      details: error,
    };
    throw apiError;
  }

  // Cast through unknown because database.types.ts is a placeholder.
  // Once full types are generated, these casts can be removed.
  return (data ?? []) as unknown as Vendor[];
}

/**
 * Fetch a single vendor by ID.
 */
export async function fetchVendorById(id: string): Promise<Vendor> {
  const { data, error } = await supabase
    .from('vendors')
    .select('*')
    .eq('id', id)
    .single();

  if (error) {
    const apiError: ApiError = {
      message: error.message,
      code: error.code,
      status: error.code === 'PGRST116' ? 404 : 0,
      details: error,
    };
    throw apiError;
  }

  return data as unknown as Vendor;
}
