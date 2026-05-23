import { supabase } from '@/lib/supabase';
import type { ApiError } from '@/lib/api';

// ─── Types ────────────────────────────────────────────────────────────

export interface BidTemplateItem {
  id: string;
  bid_template_id: string;
  description: string;
  item_type: 'lump_sum' | 'unit_price';
  unit_of_measure: string | null;
  sort_order: number;
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
}

export interface BidTemplateDetail extends BidTemplate {
  items: BidTemplateItem[];
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

// ─── Supabase Direct Reads ────────────────────────────────────────────

/**
 * Fetch bid templates with filtering, sorting, and pagination.
 */
export async function fetchBidTemplates(
  filters?: BidTemplateListFilters
): Promise<PaginatedBidTemplates> {
  const page = filters?.page ?? 1;
  const pageSize = filters?.page_size ?? 25;
  const sortBy = filters?.sort_by ?? 'name';
  const sortDir = filters?.sort_dir ?? 'asc';

  let query = supabase
    .from('bid_templates')
    .select('*, trades(name), bid_template_items(id)', { count: 'exact' });

  if (filters?.search) {
    query = query.ilike('name', `%${filters.search}%`);
  }

  if (filters?.trade_id === 'null') {
    query = query.is('trade_id', null);
  } else if (filters?.trade_id) {
    query = query.eq('trade_id', filters.trade_id);
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

  // Transform: extract trade_name from joined trades, count items
  const rows = (data ?? []) as unknown as Record<string, unknown>[];
  const items = rows.map((row) => {
    const trades = row.trades as { name: string } | null;
    const templateItems = row.bid_template_items as { id: string }[] | null;
    return {
      id: row.id,
      name: row.name,
      trade_id: row.trade_id,
      is_lump_sum: row.is_lump_sum,
      created_by: row.created_by,
      created_at: row.created_at,
      updated_at: row.updated_at,
      trade_name: trades?.name ?? null,
      item_count: templateItems?.length ?? 0,
    } as BidTemplate;
  });

  return {
    items,
    total: count ?? 0,
    page,
    page_size: pageSize,
  };
}

/**
 * Fetch a single bid template by ID with all items.
 */
export async function fetchBidTemplateById(id: string): Promise<BidTemplateDetail> {
  const { data, error } = await supabase
    .from('bid_templates')
    .select('*, trades(name), bid_template_items(*)')
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

  const row = data as unknown as Record<string, unknown>;
  const trades = row.trades as { name: string } | null;
  const items = (row.bid_template_items as BidTemplateItem[]) ?? [];

  // Sort items by sort_order
  items.sort((a, b) => a.sort_order - b.sort_order);

  return {
    id: row.id as string,
    name: row.name as string,
    trade_id: row.trade_id as string | null,
    is_lump_sum: row.is_lump_sum as boolean,
    created_by: row.created_by as string,
    created_at: row.created_at as string,
    updated_at: row.updated_at as string,
    trade_name: trades?.name ?? null,
    item_count: items.length,
    items,
  };
}
