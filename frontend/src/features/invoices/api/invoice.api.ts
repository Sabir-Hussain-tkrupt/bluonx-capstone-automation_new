import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';

/**
 * Internal invoices (Phase 2 · Task 2.6). Everything goes through FastAPI:
 * the table is finance-restricted under RLS, and the server narrows the list so
 * non-finance uploaders see their own invoices.
 */

export type InvoiceStatus = 'received' | 'categorised' | 'in_approval' | 'approved' | 'rejected' | 'cancelled';

export interface Invoice {
  id: string;
  project_id: string;
  budget_line_id: string | null;
  vendor_id: string | null;
  payee_name: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  amount: string;
  file_name: string;
  file_size: number | null;
  status: InvoiceStatus;
  notes: string | null;
  uploaded_by: string;
  created_at: string | null;
  budget_line_name: string | null;
  uploaded_by_name: string | null;
  vendor_name: string | null;
}

export interface CategoriseResult {
  invoice_id: string;
  budget_line_id: string;
  status: InvoiceStatus;
  allowance: string;
  overage: string;
  variance_id: string | null;
  variance_line_id: string | null;
  budget_status: string;
  payment_approvals: { id: string; budget_line_id: string; amount: number | string }[];
}

export interface InvoiceUploadInput {
  file: File;
  amount: string;
  payee_name?: string;
  invoice_number?: string;
  invoice_date?: string;
  notes?: string;
}

export async function fetchInvoices(projectId: string): Promise<Invoice[]> {
  const { data } = await api.get(API_ENDPOINTS.PROJECT_INVOICES(projectId));
  return data as Invoice[];
}

export async function uploadInvoice(projectId: string, input: InvoiceUploadInput): Promise<Invoice> {
  const formData = new FormData();
  formData.append('file', input.file);
  formData.append('amount', input.amount);
  if (input.payee_name) formData.append('payee_name', input.payee_name);
  if (input.invoice_number) formData.append('invoice_number', input.invoice_number);
  if (input.invoice_date) formData.append('invoice_date', input.invoice_date);
  if (input.notes) formData.append('notes', input.notes);
  const { data } = await api.post(API_ENDPOINTS.PROJECT_INVOICES(projectId), formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  });
  return data as Invoice;
}

export async function categoriseInvoice(invoiceId: string, budgetLineId: string): Promise<CategoriseResult> {
  const { data } = await api.post(API_ENDPOINTS.INVOICE_CATEGORISE(invoiceId), { budget_line_id: budgetLineId });
  return data as CategoriseResult;
}

export async function cancelInvoice(invoiceId: string): Promise<Invoice> {
  const { data } = await api.post(API_ENDPOINTS.INVOICE_CANCEL(invoiceId));
  return data as Invoice;
}

export async function getInvoiceUrl(invoiceId: string): Promise<string> {
  const { data } = await api.get<{ url: string }>(API_ENDPOINTS.INVOICE_URL(invoiceId));
  return data.url;
}
