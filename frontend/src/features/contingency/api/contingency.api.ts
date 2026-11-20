import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  CheckpointPreview,
  CheckpointResult,
  ContingencyLedger,
  ContingencyOverview,
  ContingencySettings,
} from '../types';

// Reads and writes both go through FastAPI: the panel combines the ledger,
// buckets, top-ups and checkpoint, and works out the balance per bucket.

export async function fetchContingency(projectId: string): Promise<ContingencyOverview> {
  const { data } = await api.get<ContingencyOverview>(API_ENDPOINTS.PROJECT_CONTINGENCY(projectId));
  return data;
}

export async function fetchContingencyLedger(projectId: string): Promise<ContingencyLedger> {
  const { data } = await api.get<ContingencyLedger>(API_ENDPOINTS.PROJECT_CONTINGENCY_LEDGER(projectId));
  return data;
}

/** Download the ledger as CSV (blob → anchor click, like the budget export). */
export async function exportContingencyLedger(projectId: string): Promise<void> {
  const response = await api.get(API_ENDPOINTS.PROJECT_CONTINGENCY_LEDGER_EXPORT(projectId), {
    responseType: 'blob',
    timeout: 60_000,
  });
  const disposition: string = response.headers['content-disposition'] ?? '';
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match?.[1] ?? 'contingency-ledger.csv';
  const url = URL.createObjectURL(response.data as Blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export async function setContingencyPercent(projectId: string, percent: string | null) {
  const { data } = await api.put(API_ENDPOINTS.PROJECT_CONTINGENCY_PERCENT(projectId), {
    contingency_percent: percent,
  });
  return data;
}

export async function requestTopUp(projectId: string, body: { amount: string; reason: string }) {
  const { data } = await api.post(API_ENDPOINTS.PROJECT_CONTINGENCY_TOP_UPS(projectId), body);
  return data;
}

export async function decideTopUp(
  bucketId: string,
  body: { approve: boolean; approved_amount?: string | null; note?: string | null },
) {
  const { data } = await api.post(API_ENDPOINTS.CONTINGENCY_TOP_UP_DECISION(bucketId), body);
  return data;
}

export async function cancelTopUp(bucketId: string) {
  const { data } = await api.post(API_ENDPOINTS.CONTINGENCY_TOP_UP_CANCEL(bucketId));
  return data;
}

export async function fetchBiddingCheckpoint(projectId: string): Promise<CheckpointPreview> {
  const { data } = await api.get<CheckpointPreview>(API_ENDPOINTS.PROJECT_BIDDING_CHECKPOINT(projectId));
  return data;
}

export async function completeBidding(
  projectId: string,
  body: { note?: string | null; acknowledge_open_tasks: boolean },
): Promise<CheckpointResult> {
  const { data } = await api.post<CheckpointResult>(API_ENDPOINTS.PROJECT_BIDDING_COMPLETE(projectId), body);
  return data;
}

export async function reopenBidding(projectId: string) {
  const { data } = await api.post(API_ENDPOINTS.PROJECT_BIDDING_REOPEN(projectId));
  return data;
}

export async function fetchContingencySettings(): Promise<ContingencySettings> {
  const { data } = await api.get<ContingencySettings>(API_ENDPOINTS.CONTINGENCY_SETTINGS);
  return data;
}

export async function updateContingencySettings(body: Partial<Record<keyof ContingencySettings, string | string[]>>) {
  const { data } = await api.put<ContingencySettings>(API_ENDPOINTS.CONTINGENCY_SETTINGS, body);
  return data;
}
