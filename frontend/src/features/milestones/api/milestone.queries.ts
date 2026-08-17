import { supabase } from '@/lib/supabase';
import { fromSupabaseError } from '@/lib/api';

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

/**
 * The task's active award and everything downstream of it, in one read.
 *
 * Award-first rather than contract-first because a failed envelope send can
 * abort BEFORE the contract row is written, and a contract-keyed read renders
 * nothing at all in that state — the PM sees an award that looks fine and no
 * hint the vendor got nothing. The envelope row is the discriminator: both a
 * healthy in-flight contract and a failed send sit at award status
 * `pending_acceptance`, and `contracts.status` says nothing either, since
 * `sent_for_signature` is written inside the send before it can fail.
 */
export interface TaskAwardState {
  awardId: string;
  awardStatus: string;
  vendorCompanyName: string | null;
  contract: TaskActiveContract | null;
  hasEnvelope: boolean;
}

// ─── Supabase Direct Reads (RLS) ──────────────────────────────────────

export async function fetchMilestonesForTask(taskId: string): Promise<Milestone[]> {
  const { data, error } = await supabase
    .from('milestones')
    .select('*')
    .eq('task_id', taskId)
    .order('sort_order', { ascending: true });

  if (error) throw fromSupabaseError(error);
  return (data ?? []) as unknown as Milestone[];
}

export async function fetchMilestone(id: string): Promise<MilestoneWithResponses> {
  const { data, error } = await supabase
    .from('milestones')
    .select('*, milestone_responses(*, vendor_contacts(full_name))')
    .eq('id', id)
    .single();

  if (error) throw fromSupabaseError(error, error.code === 'PGRST116' ? 404 : 0);
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

  if (error) throw fromSupabaseError(error);
  return (data ?? []) as unknown as MilestoneEvent[];
}

/** PostgREST returns a to-one embed as an object, but a to-many as an array.
 *  Normalize both so a relationship being re-detected can't break the read. */
function embedOne<T>(value: T | T[] | null | undefined): T | null {
  if (Array.isArray(value)) return value[0] ?? null;
  return value ?? null;
}

interface AwardStateRow {
  id: string;
  status: string;
  vendors: { company_name: string } | { company_name: string }[] | null;
  contracts:
    | (TaskActiveContract & { docusign_envelopes: { id: string }[] | null })
    | (TaskActiveContract & { docusign_envelopes: { id: string }[] | null })[]
    | null;
}

// NOTE: lenient contract gate — a task is "contracted" once any non-terminated
// contract exists (mirrors idx_contracts_one_active_per_task and the backend
// milestone_service._resolve_active_contract_id). To require a SIGNED contract,
// filter contracts to .in('status', ['executed','active']) here AND in
// milestone_service._resolve_active_contract_id.
//
// One nested select carries award + vendor + contract + envelope: the chain is
// FK-connected (contracts.award_id is NOT NULL UNIQUE -> awards.id;
// docusign_envelopes.contract_id -> contracts.id), and RLS grants `authenticated`
// SELECT on all four tables. The status filter mirrors
// idx_awards_one_active_per_task, so at most one row can match and maybeSingle()
// is safe. Declined and cancelled awards are excluded outright: those tasks are
// freed for re-award, and offering to send a contract there would push one for an
// award the vendor already rejected.
export async function fetchTaskAwardState(
  taskId: string,
): Promise<TaskAwardState | null> {
  const { data, error } = await supabase
    .from('awards')
    .select(
      'id, status, vendors(company_name), ' +
        'contracts(id, status, contract_number, start_date, end_date, ' +
        'docusign_envelopes(id))',
    )
    .eq('task_id', taskId)
    .not('status', 'in', '("declined_by_vendor","cancelled")')
    .maybeSingle();

  if (error) throw fromSupabaseError(error);
  if (!data) return null;

  const row = data as unknown as AwardStateRow;
  const contractRow = embedOne(row.contracts);
  const envelopes = contractRow?.docusign_envelopes ?? [];

  return {
    awardId: row.id,
    awardStatus: row.status,
    vendorCompanyName: embedOne(row.vendors)?.company_name ?? null,
    // A terminated contract is history; treat it as absent so ContractPanel and
    // MilestonesCard keep the visibility they had under the contract-keyed read.
    contract:
      contractRow && contractRow.status !== 'terminated'
        ? {
            id: contractRow.id,
            status: contractRow.status,
            contract_number: contractRow.contract_number,
            start_date: contractRow.start_date,
            end_date: contractRow.end_date,
          }
        : null,
    hasEnvelope: envelopes.length > 0,
  };
}
