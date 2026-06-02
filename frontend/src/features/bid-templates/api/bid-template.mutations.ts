import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';

// ─── Mutation Input Types ─────────────────────────────────────────────

export interface BidTemplateItemInput {
  description: string;
  item_type: 'lump_sum' | 'unit_price';
  unit_of_measure?: string | null;
}

export interface CreateBidTemplateInput {
  name: string;
  trade_id?: string | null;
  is_lump_sum: boolean;
  items: BidTemplateItemInput[];
}

export interface UpdateBidTemplateInput {
  id: string;
  name: string;
  trade_id?: string | null;
  is_lump_sum: boolean;
  items: BidTemplateItemInput[];
}

// ─── FastAPI Write Operations ─────────────────────────────────────────

export async function createBidTemplate(input: CreateBidTemplateInput) {
  const { data } = await api.post(API_ENDPOINTS.BID_TEMPLATES, input);
  return data;
}

export async function updateBidTemplate({ id, ...input }: UpdateBidTemplateInput) {
  const { data } = await api.put(API_ENDPOINTS.BID_TEMPLATE(id), input);
  return data;
}

export async function deleteBidTemplate(id: string): Promise<void> {
  await api.delete(API_ENDPOINTS.BID_TEMPLATE(id));
}

/**
 * Deep-copy a template + all its items into a new template. The escape
 * hatch when the source is locked by a live bid package (Task 8.1).
 */
export async function duplicateBidTemplate(id: string) {
  const { data } = await api.post(API_ENDPOINTS.BID_TEMPLATE_DUPLICATE(id));
  return data as { id: string; name: string };
}
