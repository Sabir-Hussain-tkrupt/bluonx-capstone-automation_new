import { supabase } from '@/lib/supabase';
import { api, fromSupabaseError } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  BudgetLine,
  BudgetLineInput,
  BudgetSummary,
  BudgetTemplate,
  BudgetTemplateLine,
  ImportPreview,
  ImportPreviewRow,
  LandClosing,
} from '../types';

// ─── Reads (Supabase, RLS: any active user) ───────────────────────────

export async function fetchBudgetLines(projectId: string): Promise<BudgetLine[]> {
  const { data, error } = await supabase
    .from('v_budget_lines')
    .select('*')
    .eq('project_id', projectId)
    .order('sort_order', { ascending: true });
  if (error) throw fromSupabaseError(error);
  return (data ?? []) as unknown as BudgetLine[];
}

export async function fetchBudgetSummary(projectId: string): Promise<BudgetSummary | null> {
  const { data, error } = await supabase
    .from('v_project_budget_summary')
    .select('*')
    .eq('project_id', projectId)
    .maybeSingle();
  if (error) throw fromSupabaseError(error);
  return (data ?? null) as unknown as BudgetSummary | null;
}

export async function fetchLandClosings(projectId: string): Promise<LandClosing[]> {
  const { data, error } = await supabase
    .from('land_closings')
    .select('*')
    .eq('project_id', projectId)
    .order('closing_sequence', { ascending: true });
  if (error) throw fromSupabaseError(error);
  return (data ?? []) as unknown as LandClosing[];
}

export async function fetchDefaultTemplate(): Promise<{
  template: BudgetTemplate | null;
  lines: BudgetTemplateLine[];
}> {
  const { data: tmpl, error } = await supabase
    .from('budget_templates')
    .select('id, name, description, is_default')
    .eq('is_default', true)
    .eq('is_active', true)
    .is('deleted_at', null)
    .maybeSingle();
  if (error) throw fromSupabaseError(error);
  const template = (tmpl ?? null) as unknown as BudgetTemplate | null;
  if (!template) return { template: null, lines: [] };

  const { data: lines, error: linesError } = await supabase
    .from('budget_template_lines')
    .select('*')
    .eq('budget_template_id', template.id)
    .order('sort_order', { ascending: true });
  if (linesError) throw fromSupabaseError(linesError);
  return { template, lines: (lines ?? []) as unknown as BudgetTemplateLine[] };
}

// ─── Writes (FastAPI, admin only) ─────────────────────────────────────

export async function createBudget(projectId: string, body: { contingency_percent?: string } = {}) {
  const { data } = await api.post(API_ENDPOINTS.PROJECT_BUDGET(projectId), body);
  return data as { line_count: number };
}

export async function baselineBudget(projectId: string) {
  const { data } = await api.post(API_ENDPOINTS.PROJECT_BUDGET_BASELINE(projectId));
  return data as { budget_status: string; approved_budget_total: number | string };
}

export async function resetBudget(projectId: string) {
  const { data } = await api.post(API_ENDPOINTS.PROJECT_BUDGET_RESET(projectId));
  return data as { budget_status: string };
}

export async function syncAwards(projectId: string) {
  const { data } = await api.post(API_ENDPOINTS.PROJECT_BUDGET_SYNC_AWARDS(projectId));
  return data as { applied: number; locked: number; failed: number };
}

export async function addBudgetLine(projectId: string, body: BudgetLineInput) {
  const { data } = await api.post(API_ENDPOINTS.PROJECT_BUDGET_LINES(projectId), body);
  return data;
}

export async function updateBudgetLine(lineId: string, body: BudgetLineInput) {
  const { data } = await api.patch(API_ENDPOINTS.BUDGET_LINE(lineId), body);
  return data;
}

export async function removeBudgetLine(lineId: string) {
  await api.delete(API_ENDPOINTS.BUDGET_LINE(lineId));
}

export async function reorderBudgetLines(projectId: string, lineIds: string[]) {
  const { data } = await api.put(API_ENDPOINTS.PROJECT_BUDGET_LINES_ORDER(projectId), { line_ids: lineIds });
  return data;
}

export interface ClosingInput {
  acres?: string | null;
  amount?: string;
  planned_closing_date?: string;
  actual_closing_date?: string | null;
  status?: LandClosing['status'];
  notes?: string | null;
}

export async function addLandClosing(lineId: string, body: ClosingInput) {
  const { data } = await api.post(API_ENDPOINTS.BUDGET_LINE_CLOSINGS(lineId), body);
  return data as LandClosing;
}

export async function updateLandClosing(closingId: string, body: ClosingInput) {
  const { data } = await api.patch(API_ENDPOINTS.LAND_CLOSING(closingId), body);
  return data as LandClosing;
}

/** Download the budget as a file (blob → anchor click, like document downloads). */
export async function exportBudget(projectId: string, format: 'xlsx' | 'csv'): Promise<void> {
  const response = await api.get(API_ENDPOINTS.PROJECT_BUDGET_EXPORT(projectId), {
    params: { format },
    responseType: 'blob',
    timeout: 60_000,
  });
  const disposition: string = response.headers['content-disposition'] ?? '';
  const match = /filename="([^"]+)"/.exec(disposition);
  const filename = match?.[1] ?? `budget.${format}`;
  const url = URL.createObjectURL(response.data as Blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export async function previewBudgetImport(projectId: string, file: File): Promise<ImportPreview> {
  const formData = new FormData();
  formData.append('file', file);
  const { data } = await api.post(API_ENDPOINTS.PROJECT_BUDGET_IMPORT_PREVIEW(projectId), formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60_000,
  });
  return data as ImportPreview;
}

export async function applyBudgetImport(projectId: string, rows: ImportPreviewRow[]) {
  const body = {
    rows: rows.map((r) => ({
      line_id: r.line_id,
      name: r.name,
      line_type: r.line_type,
      section_name: r.section_name,
      budget_amount: r.budget_amount,
      anticipated_start_date: r.anticipated_start_date,
      anticipated_end_date: r.anticipated_end_date,
      payment_terms_days: r.payment_terms_days ?? null,
      cash_bucket: r.cash_bucket ?? null,
    })),
  };
  const { data } = await api.post(API_ENDPOINTS.PROJECT_BUDGET_IMPORT_APPLY(projectId), body);
  return data as { updated: number; added: number };
}

// ─── Template (admin only) ────────────────────────────────────────────

export type TemplateLineInput = Partial<
  Pick<
    BudgetTemplateLine,
    'line_type' | 'line_subtype' | 'name' | 'section_name' | 'trade_id' | 'default_payment_terms_days' | 'default_cash_bucket' | 'is_active'
  >
> & { default_amount?: string | null };

export async function addTemplateLine(templateId: string, body: TemplateLineInput) {
  const { data } = await api.post(API_ENDPOINTS.BUDGET_TEMPLATE_LINES(templateId), body);
  return data as BudgetTemplateLine;
}

export async function updateTemplateLine(lineId: string, body: TemplateLineInput) {
  const { data } = await api.patch(API_ENDPOINTS.BUDGET_TEMPLATE_LINE(lineId), body);
  return data as BudgetTemplateLine;
}

export async function deleteTemplateLine(lineId: string) {
  await api.delete(API_ENDPOINTS.BUDGET_TEMPLATE_LINE(lineId));
}

export async function reorderTemplateLines(templateId: string, lineIds: string[]) {
  const { data } = await api.put(API_ENDPOINTS.BUDGET_TEMPLATE_LINES_ORDER(templateId), { line_ids: lineIds });
  return data;
}
