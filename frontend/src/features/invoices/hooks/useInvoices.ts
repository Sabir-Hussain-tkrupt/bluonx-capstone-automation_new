import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { errorMessage } from '@/lib/api';
import { useToast } from '@/components/ui/Toast/useToast';
import {
  cancelInvoice,
  categoriseInvoice,
  fetchInvoices,
  getInvoiceUrl,
  uploadInvoice,
  type InvoiceUploadInput,
} from '../api/invoice.api';

export function useInvoices(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.invoices.project(projectId),
    queryFn: () => fetchInvoices(projectId),
    enabled: !!projectId && enabled,
  });
}

/** Invoices move budget totals (invoiced / committed, overage variances). */
function useInvalidate(projectId: string) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.invoices.project(projectId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.budgets.project(projectId) });
  };
}

export function useUploadInvoice(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({ mutationFn: (input: InvoiceUploadInput) => uploadInvoice(projectId, input), onSuccess: invalidate });
}

export function useCategoriseInvoice(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({
    mutationFn: ({ invoiceId, lineId }: { invoiceId: string; lineId: string }) => categoriseInvoice(invoiceId, lineId),
    onSuccess: invalidate,
  });
}

export function useCancelInvoice(projectId: string) {
  const invalidate = useInvalidate(projectId);
  return useMutation({ mutationFn: (invoiceId: string) => cancelInvoice(invoiceId), onSuccess: invalidate });
}

/** Signed-URL download via an anchor click (same as project documents). */
export function useInvoiceDownload() {
  const { toast } = useToast();
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const download = async (invoiceId: string) => {
    setDownloadingId(invoiceId);
    try {
      const url = await getInvoiceUrl(invoiceId);
      const link = document.createElement('a');
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      toast({ variant: 'danger', message: errorMessage(error, 'Could not download the invoice.') });
    } finally {
      setDownloadingId(null);
    }
  };
  return { download, downloadingId };
}
