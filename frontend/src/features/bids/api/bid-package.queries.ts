import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import { supabase } from '@/lib/supabase';
import type { ApiError } from '@/lib/api';
import type {
  QualifiedVendorsResponse,
  BidPackageDetail,
  BidSubmissionDetail,
  EmailLogResponse,
  ProjectDocument,
  BidPackageListItem,
} from '@/features/bids/types';

// ─── FastAPI Reads (Axios) ───────────────────────────────────────────

export async function fetchQualifiedVendors(taskId: string): Promise<QualifiedVendorsResponse> {
  const { data } = await api.get<QualifiedVendorsResponse>(
    API_ENDPOINTS.TASK_QUALIFIED_VENDORS(taskId),
  );
  return data;
}

export async function fetchBidPackageDetail(id: string): Promise<BidPackageDetail> {
  const { data } = await api.get<BidPackageDetail>(API_ENDPOINTS.BID_PACKAGE(id));
  return data;
}

export async function fetchBidSubmissionDetail(id: string): Promise<BidSubmissionDetail> {
  const { data } = await api.get<BidSubmissionDetail>(API_ENDPOINTS.BID_SUBMISSION(id));
  return data;
}

export async function fetchBidPackageEmailLog(bidPackageId: string): Promise<EmailLogResponse> {
  const { data } = await api.get<EmailLogResponse>(
    API_ENDPOINTS.BID_PACKAGE_EMAIL_LOG(bidPackageId),
  );
  return data;
}

export async function fetchProjectDocuments(projectId: string): Promise<ProjectDocument[]> {
  const { data } = await api.get<ProjectDocument[]>(API_ENDPOINTS.PROJECT_DOCUMENTS(projectId));
  return data;
}

// ─── Supabase Direct Read ────────────────────────────────────────────

export async function fetchBidPackagesForTask(taskId: string): Promise<BidPackageListItem[]> {
  const { data, error } = await supabase
    .from('bid_packages')
    .select('id, task_id, round_number, deadline, status, created_at, bid_invitations(id, status)')
    .eq('task_id', taskId)
    .order('round_number', { ascending: false });

  if (error) {
    const apiError: ApiError = {
      message: error.message,
      code: error.code,
      status: 0,
      details: error,
    };
    throw apiError;
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return ((data ?? []) as any[]).map((row: Record<string, unknown>) => {
    const invitations = (row.bid_invitations as { id: string; status: string }[]) ?? [];
    return {
      id: row.id as string,
      task_id: row.task_id as string,
      round_number: row.round_number as number,
      deadline: row.deadline as string,
      status: row.status as string,
      created_at: row.created_at as string,
      invitation_total: invitations.length,
      invitation_submitted: invitations.filter((i) => i.status === 'submitted').length,
    };
  });
}
