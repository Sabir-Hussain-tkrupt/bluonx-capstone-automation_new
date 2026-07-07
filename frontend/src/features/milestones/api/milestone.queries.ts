import { supabase } from '@/lib/supabase';
import type { ApiError } from '@/lib/api';

// ─── Types ────────────────────────────────────────────────────────────

export type MilestoneStatus =
  | 'scheduled'
  | 'in_progress'
  | 'delayed'
  | 'unresponsive'
  | 'completed'
  | 'cancelled';

export interface Milestone {
  id: string;
  task_id: string;
  contract_id: string;
  name: string;
  start_date: string;
  end_date: string;
  actual_start_date: string | null;
  actual_end_date: string | null;
  status: MilestoneStatus;
  sort_order: number;
  notes: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface MilestoneResponseRecord {
  id: string;
  milestone_id: string;
  response_type: string;
  response_value: string;
  responded_at: string;
  vendor_contacts: { full_name: string } | null;
}

export interface MilestoneWithResponses extends Milestone {
  milestone_responses: MilestoneResponseRecord[];
}

/** The task's single active contract (status <> 'terminated'), or null. */
export interface TaskActiveContract {
  id: string;
  status: string;
  contract_number: string;
  start_date: string | null;
  end_date: string | null;
}

function toApiError(error: { message: string; code?: string }): ApiError {
  return {
    message: error.message,
    code: error.code ?? 'SUPABASE_ERROR',
    status: 0,
    details: error,
  };
}

// ─── Supabase Direct Reads (RLS) ──────────────────────────────────────

export async function fetchMilestonesForTask(taskId: string): Promise<Milestone[]> {
  const { data, error } = await supabase
    .from('milestones')
    .select('*')
    .eq('task_id', taskId)
    .order('sort_order', { ascending: true });

  if (error) throw toApiError(error);
  return (data ?? []) as unknown as Milestone[];
}

export async function fetchMilestone(id: string): Promise<MilestoneWithResponses> {
  const { data, error } = await supabase
    .from('milestones')
    .select('*, milestone_responses(*, vendor_contacts(full_name))')
    .eq('id', id)
    .single();

  if (error) {
    const apiError = toApiError(error);
    apiError.status = error.code === 'PGRST116' ? 404 : 0;
    throw apiError;
  }
  return data as unknown as MilestoneWithResponses;
}

// NOTE: lenient contract gate — a task is "contracted" once any non-terminated
// contract exists (mirrors idx_contracts_one_active_per_task and the backend
// milestone_service._resolve_active_contract_id). To require a SIGNED contract,
// change .neq('status','terminated') to .in('status', ['executed','active'])
// here AND in milestone_service._resolve_active_contract_id.
export async function fetchTaskActiveContract(
  taskId: string,
): Promise<TaskActiveContract | null> {
  const { data, error } = await supabase
    .from('contracts')
    .select('id, status, contract_number, start_date, end_date')
    .eq('task_id', taskId)
    .neq('status', 'terminated')
    .maybeSingle();

  if (error) throw toApiError(error);
  return (data as unknown as TaskActiveContract | null) ?? null;
}
