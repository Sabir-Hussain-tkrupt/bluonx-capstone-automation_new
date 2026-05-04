import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';

// ─── Types ────────────────────────────────────────────────────────────

export type BidPackageListStatus = 'open' | 'closed' | 'evaluating' | 'cancelled';
export type BidPackageListSortBy = 'deadline' | 'created_at' | 'project_name';
export type BidPackageListSortOrder = 'asc' | 'desc';

export interface BidPackageListFilters {
  status?: BidPackageListStatus;
  project_id?: string;
  sort_by?: BidPackageListSortBy;
  sort_order?: BidPackageListSortOrder;
}

/**
 * Cross-project bid package row returned by GET /v1/bid-packages.
 *
 * Distinct from `BidPackageListItem` in `@/features/bids/types`, which is
 * the task-scoped Supabase shape used by the task detail view.
 */
export interface BidPackagesListRow {
  id: string;
  task_id: string;
  task_name: string;
  project_id: string;
  project_name: string;
  round_number: number;
  deadline: string;
  status: BidPackageListStatus;
  total_invitations: number;
  submitted_count: number;
  created_at: string;
}

// ─── Fetcher ──────────────────────────────────────────────────────────

export async function fetchBidPackagesList(
  filters?: BidPackageListFilters,
): Promise<BidPackagesListRow[]> {
  const { data } = await api.get<{ items: BidPackagesListRow[] }>(
    API_ENDPOINTS.BID_PACKAGES,
    { params: filters },
  );
  return data.items;
}
