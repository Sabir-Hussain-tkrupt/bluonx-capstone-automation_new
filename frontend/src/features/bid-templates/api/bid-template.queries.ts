import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';

// ─── Types ────────────────────────────────────────────────────────────

export interface BidTemplateItem {
  id: string;
  bid_template_id: string;
  description: string;
  item_type: 'lump_sum' | 'unit_price';
  unit_of_measure: string | null;
  sort_order: number;
}

export interface ReferencingPackageSummary {
  id: string;
  task_name: string;
  status: string;
}

export interface BidTemplate {
  id: string;
  name: string;
  trade_id: string | null;
  is_lump_sum: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
  trade_name: string | null;
  item_count: number;
  /**
   * True iff any non-cancelled bid_package references this template.
   * When true, the template is frozen: edits/deletes are blocked
   * server-side to keep all vendor bids in the live round comparable.
   * (Task 8.1 freeze guards.) Escape hatch: duplicate the template.
   */
  is_in_use: boolean;
}

export interface BidTemplateDetail extends BidTemplate {
  items: BidTemplateItem[];
  /**
   * Live (non-cancelled) packages locking this template, capped server-side
   * (currently first 3) so heavily-used templates don't ship thousands of rows.
   * Use `referencing_packages_total` for the honest count.
   */
  referencing_packages: ReferencingPackageSummary[];
  referencing_packages_total: number;
}

export interface BidTemplateListFilters {
  search?: string;
  trade_id?: string; // UUID or 'null' for general-purpose
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface PaginatedBidTemplates {
  items: BidTemplate[];
  total: number;
  page: number;
  page_size: number;
}

// ─── FastAPI Reads ────────────────────────────────────────────────────
//
// We route both list and detail through FastAPI rather than reading from
// Supabase directly so that `is_in_use` is derived by the same code path
// that enforces the edit guard. The earlier Supabase-direct version
// embedded `bid_packages(...)` to compute the flag client-side, but RLS
// on `bid_packages`/`tasks` silently filtered the embed to `[]` for
// `authenticated`, leaving locked templates rendering as editable.

/**
 * Fetch bid templates with filtering, sorting, and pagination.
 */
export async function fetchBidTemplates(
  filters?: BidTemplateListFilters,
): Promise<PaginatedBidTemplates> {
  const params: Record<string, string | number> = {
    page: filters?.page ?? 1,
    page_size: filters?.page_size ?? 25,
    sort_by: filters?.sort_by ?? 'name',
    sort_dir: filters?.sort_dir ?? 'asc',
  };

  if (filters?.search) params.search = filters.search;
  if (filters?.trade_id) params.trade_id = filters.trade_id;

  const { data } = await api.get(API_ENDPOINTS.BID_TEMPLATES, { params });
  return data as PaginatedBidTemplates;
}

/**
 * Fetch a single bid template by ID with all items.
 */
export async function fetchBidTemplateById(
  id: string,
): Promise<BidTemplateDetail> {
  const { data } = await api.get(API_ENDPOINTS.BID_TEMPLATE(id));
  return data as BidTemplateDetail;
}
