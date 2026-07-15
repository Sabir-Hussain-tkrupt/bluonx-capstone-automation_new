import { supabase } from '@/lib/supabase';
import type { ApiError } from '@/lib/api';
import type { MilestoneStatus } from '@/features/milestones/api/milestone.queries';

// ─── Types ────────────────────────────────────────────────────────────

/**
 * One row of the `v_milestone_overview` DB view: milestone + task + project +
 * vendor + creator, denormalized for cross-project read surfaces. The view
 * inner-joins contracts/vendors, so every row is guaranteed a contract, vendor,
 * task, and project. `days_paused` is NULL for non-paused milestones.
 */
export interface MilestoneOverviewRow {
  milestone_id: string;
  milestone_name: string;
  status: MilestoneStatus;
  cycle_number: number;
  sort_order: number;
  start_date: string;
  end_date: string;
  baseline_end_date: string;
  actual_start_date: string | null;
  actual_end_date: string | null;
  end_date_moved: boolean;
  days_late: number | null;
  is_overdue: boolean;
  paused_since: string | null;
  days_paused: number | null;
  task_id: string;
  task_name: string;
  project_id: string;
  project_name: string;
  contract_id: string;
  vendor_id: string;
  vendor_company_name: string;
  created_by: string;
  created_by_name: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

/** The two statuses that pause the check-in cycle and wait on a human. */
export const PAUSED_STATUSES = ['delayed', 'unresponsive'] as const;

export interface MilestoneOverviewFilters {
  search?: string;
  /** A single milestone status, OR the 'attention' pseudo-status (delayed + unresponsive). */
  status?: string;
  project_id?: string;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface PaginatedMilestoneOverview {
  items: MilestoneOverviewRow[];
  total: number;
  page: number;
  page_size: number;
}

const VIEW = 'v_milestone_overview';

function toApiError(error: { message: string; code?: string }): ApiError {
  return {
    message: error.message,
    code: error.code ?? 'SUPABASE_ERROR',
    status: 0,
    details: error,
  };
}

// ─── Supabase Direct Reads (RLS via security_invoker view) ────────────

/**
 * Fetch the cross-project milestone list with search, status/project filters,
 * server-side sort, and offset pagination. Mirrors `fetchVendors`.
 *
 * Default sort surfaces the stalled milestones first: `days_paused` DESC with
 * NULLs last (non-paused rows sink), then `end_date` ASC. Any explicit column
 * sort replaces that with a single ordering.
 */
export async function fetchMilestoneOverview(
  filters?: MilestoneOverviewFilters,
): Promise<PaginatedMilestoneOverview> {
  const page = filters?.page ?? 1;
  const pageSize = filters?.page_size ?? 25;

  let query = supabase.from(VIEW).select('*', { count: 'exact' });

  if (filters?.search) {
    const q = filters.search;
    query = query.or(
      `milestone_name.ilike.%${q}%,task_name.ilike.%${q}%,project_name.ilike.%${q}%,vendor_company_name.ilike.%${q}%`,
    );
  }

  if (filters?.status === 'attention') {
    query = query.in('status', PAUSED_STATUSES as unknown as string[]);
  } else if (filters?.status) {
    query = query.eq('status', filters.status);
  }

  if (filters?.project_id) {
    query = query.eq('project_id', filters.project_id);
  }

  // Sorting: an explicit column overrides the stalled-first default. NULLs sort
  // last regardless of direction so non-paused rows never float to the top.
  if (filters?.sort_by) {
    query = query.order(filters.sort_by, {
      ascending: (filters.sort_dir ?? 'asc') !== 'desc',
      nullsFirst: false,
    });
    // Sorting on days_paused keeps end_date as the tiebreaker (stalled-first view).
    if (filters.sort_by === 'days_paused') {
      query = query.order('end_date', { ascending: true });
    }
  } else {
    query = query
      .order('days_paused', { ascending: false, nullsFirst: false })
      .order('end_date', { ascending: true });
  }

  const offset = (page - 1) * pageSize;
  query = query.range(offset, offset + pageSize - 1);

  const { data, error, count } = await query;
  if (error) throw toApiError(error);

  return {
    items: (data ?? []) as unknown as MilestoneOverviewRow[],
    total: count ?? 0,
    page,
    page_size: pageSize,
  };
}

/**
 * Fetch all milestones for one project (no pagination), grouped-ready for the
 * timeline: ordered by task name, then the milestone's sort order within a task.
 */
export async function fetchProjectTimelineMilestones(
  projectId: string,
): Promise<MilestoneOverviewRow[]> {
  const { data, error } = await supabase
    .from(VIEW)
    .select('*')
    .eq('project_id', projectId)
    .order('task_name', { ascending: true })
    .order('sort_order', { ascending: true });

  if (error) throw toApiError(error);
  return (data ?? []) as unknown as MilestoneOverviewRow[];
}

export interface PausedMilestonesParams {
  /** Restrict to a single creator (the dashboard "Mine only" toggle). */
  createdBy?: string;
  /** Cap the number of rows fetched (the card only renders a handful). */
  limit?: number;
}

/**
 * Fetch paused (delayed/unresponsive) milestones across all projects,
 * worst-stalled first. The dashboard card only shows a few rows, so it passes a
 * `limit`: the payload stays flat no matter how many milestones stall. Use
 * `fetchPausedMilestonesCount` for the true total (badge / "View all").
 */
export async function fetchPausedMilestones(
  params: PausedMilestonesParams = {},
): Promise<MilestoneOverviewRow[]> {
  let query = supabase
    .from(VIEW)
    .select('*')
    .in('status', PAUSED_STATUSES as unknown as string[])
    .order('days_paused', { ascending: false, nullsFirst: false });

  if (params.createdBy) query = query.eq('created_by', params.createdBy);
  if (params.limit != null) query = query.limit(params.limit);

  const { data, error } = await query;
  if (error) throw toApiError(error);
  return (data ?? []) as unknown as MilestoneOverviewRow[];
}

/**
 * Exact count of paused milestones (optionally for one creator), fetched
 * head-only so no rows cross the wire. Stays accurate past Supabase's default
 * 1000-row response cap, unlike counting a fetched array. Powers the sidebar
 * badge and the card's count / "View all N".
 */
export async function fetchPausedMilestonesCount(
  params: { createdBy?: string } = {},
): Promise<number> {
  let query = supabase
    .from(VIEW)
    .select('*', { count: 'exact', head: true })
    .in('status', PAUSED_STATUSES as unknown as string[]);

  if (params.createdBy) query = query.eq('created_by', params.createdBy);

  const { count, error } = await query;
  if (error) throw toApiError(error);
  return count ?? 0;
}
