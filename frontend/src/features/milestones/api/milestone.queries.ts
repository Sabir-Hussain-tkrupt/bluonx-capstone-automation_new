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
  /** The originally committed finish. A reschedule moves end_date but never this;
   *  the gap between end_date and baseline_end_date IS the drift. */
  baseline_end_date: string;
  actual_start_date: string | null;
  actual_end_date: string | null;
  status: MilestoneStatus;
  /** Generation counter, +1 on every reschedule (staleness-kills check-in tokens). */
  cycle_number: number;
  sort_order: number;
  notes: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

/** One immutable row from the append-only milestone_events ledger. actor kind is
 *  implied by trigger_type (there is no actor_type column). Actual dates are NOT
 *  on the event — the milestone row stays authoritative for them; the note carries
 *  a human-readable snapshot instead. */
export interface MilestoneEvent {
  id: string;
  milestone_id: string;
  from_status: MilestoneStatus | null;
  to_status: MilestoneStatus;
  trigger_type: 'creation' | 'vendor_response' | 'pm_action' | 'system_no_response';
  cycle_number: number | null;
  working_end_date: string | null;
  note: string | null;
  created_at: string;
  /** Joined actor (PM/admin) for pm_action / creation events. */
  actor: { full_name: string } | null;
  /** Joined actor (vendor contact) for vendor_response events. */
  actor_vendor: { full_name: string } | null;
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

// The unified PM activity timeline. Reads the append-only ledger directly under
// RLS (milestone_events grants SELECT to any active authenticated user), newest
// first. Two actor FKs point at the same-named tables, so each is disambiguated
// by its FK column (alias:fk_column form).
export async function fetchMilestoneEvents(milestoneId: string): Promise<MilestoneEvent[]> {
  const { data, error } = await supabase
    .from('milestone_events')
    .select(
      '*, actor:actor_user_id(full_name), actor_vendor:actor_vendor_contact_id(full_name)',
    )
    .eq('milestone_id', milestoneId)
    .order('created_at', { ascending: false });

  if (error) throw toApiError(error);
  return (data ?? []) as unknown as MilestoneEvent[];
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
