import { supabase } from '@/lib/supabase';
import type { ApiError } from '@/lib/api';

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

// ─── Supabase Direct Reads ────────────────────────────────────────────

export async function fetchTasks(filters: TaskListFilters): Promise<PaginatedTasks> {
  const page = filters.page ?? 1;
  const pageSize = filters.page_size ?? 50;
  const sortBy = filters.sort_by ?? 'sort_order';
  const ascending = (filters.sort_dir ?? 'asc') !== 'desc';

  let query = supabase
    .from('tasks')
    .select('*, trades(name)', { count: 'exact' })
    .eq('project_id', filters.projectId)
    .is('deleted_at', null);

  if (filters.search) {
    query = query.ilike('name', `%${filters.search}%`);
  }

  if (filters.status) {
    query = query.eq('status', filters.status);
  }

  query = query.order(sortBy, { ascending });

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

  // Flatten trade join
  const items = (data ?? []).map((row: Record<string, unknown>) => {
    const trades = row.trades as { name: string } | null;
    const { trades: _trades, ...rest } = row;
    return { ...rest, trade_name: trades?.name ?? null } as unknown as Task;
  });

  return {
    items,
    total: count ?? 0,
    page,
    page_size: pageSize,
  };
}

export async function fetchTaskById(projectId: string, taskId: string): Promise<Task> {
  const { data, error } = await supabase
    .from('tasks')
    .select('*, trades(name)')
    .eq('id', taskId)
    .eq('project_id', projectId)
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

  const trades = (data as Record<string, unknown>).trades as { name: string } | null;
  const { trades: _trades, ...rest } = data as Record<string, unknown>;
  return { ...rest, trade_name: trades?.name ?? null } as unknown as Task;
}

export async function fetchActiveTrades(): Promise<Trade[]> {
  const { data, error } = await supabase
    .from('trades')
    .select('id, name, phase, is_active')
    .eq('is_active', true)
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
