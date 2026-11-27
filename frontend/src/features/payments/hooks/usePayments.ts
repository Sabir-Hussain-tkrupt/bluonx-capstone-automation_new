import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { queryKeys } from '@/lib/queryKeys';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  ApproverSettings,
  FinanceHandoff,
  LinePayments,
  Payment,
  PaymentDetail,
  PaymentRequestInput,
} from '../types';

export type PaymentScope = 'queue' | 'pending' | 'rejected' | 'sent' | 'all';

export function usePayments(scope: PaymentScope, projectId?: string) {
  const params = { scope, ...(projectId ? { project_id: projectId } : {}) };
  return useQuery({
    queryKey: queryKeys.payments.list(params),
    queryFn: async () => (await api.get<Payment[]>(API_ENDPOINTS.PAYMENT_APPROVALS, { params })).data,
  });
}

export function usePayment(id: string) {
  return useQuery({
    queryKey: queryKeys.payments.detail(id),
    queryFn: async () => (await api.get<PaymentDetail>(API_ENDPOINTS.PAYMENT_APPROVAL(id))).data,
    enabled: !!id,
  });
}

export function useLinePayments(lineId: string) {
  return useQuery({
    queryKey: queryKeys.payments.line(lineId),
    queryFn: async () => (await api.get<LinePayments>(API_ENDPOINTS.BUDGET_LINE_PAYMENTS(lineId))).data,
    enabled: !!lineId,
  });
}

export function useFinanceHandoffs(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.payments.handoffs(),
    queryFn: async () => (await api.get<FinanceHandoff[]>(API_ENDPOINTS.FINANCE_HANDOFFS)).data,
    enabled,
  });
}

/** Payments move budgets, variances, invoices and health: refresh them all. */
function useInvalidate() {
  const queryClient = useQueryClient();
  return () => {
    for (const key of [queryKeys.payments.all, queryKeys.budgets.all, queryKeys.variances.all, queryKeys.invoices.all]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };
}

export function useRequestPayment(lineId: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async (body: PaymentRequestInput) =>
      (await api.post<Payment>(API_ENDPOINTS.BUDGET_LINE_PAYMENTS(lineId), body)).data,
    onSuccess,
  });
}

type Action = 'approve' | 'reject' | 'resubmit' | 'cancel';

export function usePaymentAction(id: string) {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async ({ action, body }: { action: Action; body: Record<string, unknown> }) =>
      (await api.post<Payment>(`${API_ENDPOINTS.PAYMENT_APPROVAL(id)}/${action}`, body)).data,
    onSuccess,
  });
}

export function useResendHandoff() {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async (id: string) => (await api.post(API_ENDPOINTS.FINANCE_HANDOFF_RESEND(id))).data,
    onSuccess,
  });
}

export function useMarkExported() {
  const onSuccess = useInvalidate();
  return useMutation({
    mutationFn: async (ids: string[]) =>
      (await api.post<{ updated: number }>(API_ENDPOINTS.FINANCE_HANDOFFS_MARK_EXPORTED, { handoff_ids: ids })).data,
    onSuccess,
  });
}

export async function downloadHandoffs(format: 'csv' | 'xlsx' | 'quickbooks', onlyPending: boolean) {
  const response = await api.get(API_ENDPOINTS.FINANCE_HANDOFFS_EXPORT, {
    params: { format, only_pending: onlyPending },
    responseType: 'blob',
    timeout: 60_000,
  });
  const match = /filename="([^"]+)"/.exec(response.headers['content-disposition'] ?? '');
  const url = URL.createObjectURL(response.data as Blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = match?.[1] ?? `finance-handoffs.${format === 'xlsx' ? 'xlsx' : 'csv'}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function openHandoffDocument(id: string) {
  const { data } = await api.get<{ url: string }>(API_ENDPOINTS.FINANCE_HANDOFF_DOCUMENT(id));
  window.open(data.url, '_blank', 'noopener');
}

export function useApproverSettings(enabled = true) {
  return useQuery({
    queryKey: queryKeys.payments.approvers(),
    queryFn: async () => (await api.get<ApproverSettings[]>(API_ENDPOINTS.APPROVER_SETTINGS)).data,
    enabled,
  });
}

export function useUpdateApproverSettings(userId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: Record<string, unknown>) =>
      (await api.put<ApproverSettings>(API_ENDPOINTS.USER_APPROVER_SETTINGS(userId), body)).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.payments.approvers() }),
  });
}
