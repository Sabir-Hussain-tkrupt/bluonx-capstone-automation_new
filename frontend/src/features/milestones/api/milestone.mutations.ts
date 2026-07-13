import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { Milestone } from '@/features/milestones/api/milestone.queries';

// ─── Mutation Input Types ─────────────────────────────────────────────

export interface CreateMilestoneInput {
  task_id: string;
  name: string;
  start_date: string;
  end_date: string;
  notes?: string | null;
}

export interface UpdateMilestoneInput {
  id: string;
  name?: string;
  start_date?: string;
  end_date?: string;
  notes?: string | null;
  sort_order?: number;
}

// ─── FastAPI Write Operations ─────────────────────────────────────────

export async function createMilestone(input: CreateMilestoneInput): Promise<Milestone> {
  const { data } = await api.post<Milestone>(API_ENDPOINTS.MILESTONES, input);
  return data;
}

export async function updateMilestone({ id, ...input }: UpdateMilestoneInput): Promise<Milestone> {
  const { data } = await api.patch<Milestone>(API_ENDPOINTS.MILESTONE(id), input);
  return data;
}

export async function deleteMilestone(id: string): Promise<void> {
  await api.delete(API_ENDPOINTS.MILESTONE(id));
}

export async function markMilestoneStarted(
  id: string,
  actualStartDate?: string | null,
): Promise<Milestone> {
  const { data } = await api.post<Milestone>(API_ENDPOINTS.MILESTONE_MARK_STARTED(id), {
    actual_start_date: actualStartDate ?? null,
  });
  return data;
}

export async function markMilestoneCompleted(
  id: string,
  actualEndDate?: string | null,
): Promise<Milestone> {
  const { data } = await api.post<Milestone>(API_ENDPOINTS.MILESTONE_MARK_COMPLETED(id), {
    actual_end_date: actualEndDate ?? null,
  });
  return data;
}

export async function rescheduleMilestone(id: string, endDate: string): Promise<Milestone> {
  const { data } = await api.post<Milestone>(API_ENDPOINTS.MILESTONE_RESCHEDULE(id), {
    end_date: endDate,
  });
  return data;
}

export async function cancelMilestone(id: string): Promise<Milestone> {
  const { data } = await api.post<Milestone>(API_ENDPOINTS.MILESTONE_CANCEL(id));
  return data;
}
