import { supabase } from '@/lib/supabase';
import { api, type ApiError } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';

// ─── Types ────────────────────────────────────────────────────────────

export interface Vendor {
  id: string;
  company_name: string;
  address: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  latitude: number | null;
  longitude: number | null;
  insurance_expiration_date: string | null;
  insurance_coverage_amount: number | null;
  bonding_capacity: number | null;
  max_active_jobs: number | null;
  current_active_jobs: number;
  onboarding_status: 'pending' | 'partial' | 'complete';
  status: 'active' | 'inactive' | 'suspended';
  notes: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface VendorContact {
  id: string;
  vendor_id: string;
  full_name: string;
  email: string;
  phone: string | null;
  title: string | null;
  is_primary: boolean;
  created_at: string;
  updated_at: string;
}

export interface VendorTradeWithName {
  id: string;
  vendor_id: string;
  trade_id: string;
  trades: { name: string; phase: string } | null;
  created_at: string;
}

export interface VendorDocument {
  id: string;
  vendor_id: string;
  document_type: 'w9' | 'insurance_certificate' | 'master_trade_agreement';
  file_name: string;
  file_path: string;
  file_size: number | null;
  expiration_date: string | null;
  status: 'valid' | 'expired' | 'pending_review';
  uploaded_by: string;
  uploaded_at: string;
  updated_at: string;
}

export interface VendorFlag {
  id: string;
  vendor_id: string;
  flagged_by: string;
  reason: 'missed_deadline' | 'poor_quality' | 'unresponsive' | 'other';
  notes: string | null;
  milestone_id: string | null;
  is_resolved: boolean;
  resolved_at: string | null;
  resolved_by: string | null;
  created_at: string;
}

export interface VendorDetail extends Vendor {
  vendor_contacts: VendorContact[];
  vendor_trades: VendorTradeWithName[];
  vendor_documents: VendorDocument[];
  vendor_flags: VendorFlag[];
}

export interface Trade {
  id: string;
  name: string;
  phase: 'due_diligence' | 'development' | 'both';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface VendorListFilters {
  search?: string;
  status?: string;
  onboarding_status?: string;
  trade_id?: string;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface PaginatedVendors {
  items: Vendor[];
  total: number;
  page: number;
  page_size: number;
}

// ─── Supabase Direct Reads ────────────────────────────────────────────

/**
 * Fetch vendors with filtering, sorting, and pagination.
 */
export async function fetchVendors(filters?: VendorListFilters): Promise<PaginatedVendors> {
  const page = filters?.page ?? 1;
  const pageSize = filters?.page_size ?? 25;
  const sortBy = filters?.sort_by ?? 'company_name';
  const sortDir = filters?.sort_dir ?? 'asc';

  // If filtering by trade, first get vendor IDs with that trade
  let vendorIdsForTrade: string[] | null = null;
  if (filters?.trade_id) {
    const { data: tradeData } = await supabase
      .from('vendor_trades')
      .select('vendor_id')
      .eq('trade_id', filters.trade_id);

    vendorIdsForTrade = (tradeData ?? []).map((r: unknown) => (r as { vendor_id: string }).vendor_id);
    if (vendorIdsForTrade.length === 0) {
      return { items: [], total: 0, page, page_size: pageSize };
    }
  }

  let query = supabase
    .from('vendors')
    .select('*', { count: 'exact' })
    .is('deleted_at', null);

  if (filters?.search) {
    query = query.ilike('company_name', `%${filters.search}%`);
  }

  if (filters?.status) {
    query = query.eq('status', filters.status);
  }

  if (filters?.onboarding_status) {
    query = query.eq('onboarding_status', filters.onboarding_status);
  }

  if (vendorIdsForTrade) {
    query = query.in('id', vendorIdsForTrade);
  }

  // Sorting
  const ascending = sortDir !== 'desc';
  query = query.order(sortBy, { ascending });

  // Pagination
  const offset = (page - 1) * pageSize;
  query = query.range(offset, offset + pageSize - 1);

  const { data, error, count } = await query;

  if (error) {
    const apiError: ApiError = {
      message: error.message,
      code: error.code,
      status: 0,
      details: error,
    };
    throw apiError;
  }

  return {
    items: (data ?? []) as unknown as Vendor[],
    total: count ?? 0,
    page,
    page_size: pageSize,
  };
}

/**
 * Fetch a single vendor by ID with all related data.
 */
export async function fetchVendorById(id: string): Promise<VendorDetail> {
  const { data, error } = await supabase
    .from('vendors')
    .select(
      '*, vendor_contacts(*), vendor_trades(*, trades(name, phase)), vendor_documents(*), vendor_flags(*)'
    )
    .eq('id', id)
    .is('deleted_at', null)
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

  return data as unknown as VendorDetail;
}

/**
 * Fetch all active trades.
 */
export async function fetchTrades(): Promise<Trade[]> {
  const { data, error } = await supabase
    .from('trades')
    .select('*')
    .eq('is_active', true)
    .order('phase')
    .order('name');

  if (error) {
    const apiError: ApiError = {
      message: error.message,
      code: error.code,
      status: 0,
      details: error,
    };
    throw apiError;
  }

  return (data ?? []) as unknown as Trade[];
}

export interface InsuranceExpiringCountResponse {
  count: number;
}

/**
 * Fetch the count of active vendors whose insurance expires within 30
 * days (or has already lapsed). Backend route — uses the FastAPI client,
 * not Supabase, so the cutoff stays server-computed.
 */
export async function fetchInsuranceExpiringCount(): Promise<InsuranceExpiringCountResponse> {
  const { data } = await api.get<InsuranceExpiringCountResponse>(
    API_ENDPOINTS.VENDORS_INSURANCE_EXPIRING_COUNT,
  );
  return data;
}
