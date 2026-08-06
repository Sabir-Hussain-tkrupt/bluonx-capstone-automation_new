import { supabase } from '@/lib/supabase';
import { api, fromSupabaseError } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import { toNumberOrNull } from '@/lib/format';

// ─── Types ────────────────────────────────────────────────────────────

export type TaskStatus = 'draft' | 'bidding' | 'evaluating' | 'awarded' | 'in_progress' | 'completed' | 'cancelled';
export type TaskPhase = 'due_diligence' | 'development';
export type TaskBidType = 'competitive' | 'direct_assign' | 'internal';

export interface Task {
  id: string;
  project_id: string;
  trade_id: string;
  name: string;
  description: string | null;
  phase: TaskPhase;
  bid_type: TaskBidType;
  budget_estimate: number | null;
  sort_order: number;
  status: TaskStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  trade_name?: string | null;
}

export interface TaskListFilters {
  projectId: string;
  search?: string;
  status?: string;
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface PaginatedTasks {
  items: Task[];
  total: number;
  page: number;
  page_size: number;
}

export interface Trade {
  id: string;
  name: string;
  phase: 'due_diligence' | 'development' | 'both';
  is_active: boolean;
}

// ─── Reads ────────────────────────────────────────────────────────────

/** budget_estimate reaches the client as a string over FastAPI; pin to number. */
function normalizeTask(row: Task): Task {
  return { ...row, budget_estimate: toNumberOrNull(row.budget_estimate) };
}

/**
 * Fetch a project's tasks through the hardened FastAPI endpoint rather than a
 * direct Supabase read. GET /projects/{id}/tasks already enforces the sort
 * allow-list, LIKE-metacharacter escaping, page-size ceiling and a count-first
 * fetch, and flattens trade_name server-side. Reading Supabase directly meant
 * re-implementing all of that in a second place. Detail reads still go direct
 * (see fetchTaskById).
 */
export async function fetchTasks(filters: TaskListFilters): Promise<PaginatedTasks> {
  const { data } = await api.get<PaginatedTasks>(API_ENDPOINTS.PROJECT_TASKS(filters.projectId), {
    params: {
      search: filters.search || undefined,
      status: filters.status || undefined,
      sort_by: filters.sort_by,
      sort_dir: filters.sort_dir,
      page: filters.page,
      page_size: filters.page_size,
    },
  });

  return { ...data, items: (data.items ?? []).map(normalizeTask) };
}

export async function fetchTaskById(projectId: string, taskId: string): Promise<Task> {
  const { data, error } = await supabase
    .from('tasks')
    .select('*, trades(name)')
    .eq('id', taskId)
    .eq('project_id', projectId)
    .is('deleted_at', null)
    .single();

  if (error) throw fromSupabaseError(error, error.code === 'PGRST116' ? 404 : 0);

  const row = data as unknown as Record<string, unknown>;
  const trades = row.trades as { name: string } | null;
  const { trades: _trades, ...rest } = row;
  return normalizeTask({ ...rest, trade_name: trades?.name ?? null } as unknown as Task);
}

export async function fetchActiveTrades(): Promise<Trade[]> {
  const { data, error } = await supabase
    .from('trades')
    .select('id, name, phase, is_active')
    .eq('is_active', true)
    .order('name');

  if (error) throw fromSupabaseError(error);

  return (data ?? []) as unknown as Trade[];
}
