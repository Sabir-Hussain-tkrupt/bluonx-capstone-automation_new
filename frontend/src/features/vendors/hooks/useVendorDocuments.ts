import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { useToast } from '@/components/ui/Toast/useToast';
import {
  uploadVendorDocument,
  deleteVendorDocument,
  getVendorDocumentUrl,
} from '@/features/vendors/api/vendor-documents.mutations';

export function useUploadVendorDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ vendorId, formData }: { vendorId: string; formData: FormData }) =>
      uploadVendorDocument(vendorId, formData),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.vendors.detail(variables.vendorId),
      });
    },
  });
}

export function useDeleteVendorDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ vendorId, docId }: { vendorId: string; docId: string }) =>
      deleteVendorDocument(vendorId, docId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.vendors.detail(variables.vendorId),
      });
    },
  });
}

export function useVendorDocumentDownload() {
  const { toast } = useToast();
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const download = async (vendorId: string, docId: string) => {
    setDownloadingId(docId);
    try {
      const url = await getVendorDocumentUrl(vendorId, docId);

      // An anchor click keeps this within the user's original gesture.
      // window.open() after an await is treated as programmatic by Chrome and
      // Safari and gets caught by the popup blocker, which looked to the user
      // like the download silently doing nothing.
      const link = document.createElement('a');
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      // Previously try/finally with no catch: a failed signed-URL request
      // cleared the spinner and told the user nothing at all.
      toast({
        variant: 'danger',
        message:
          (error as { message?: string })?.message ?? 'Could not download the document.',
      });
    } finally {
      setDownloadingId(null);
    }
  };

  return { download, downloadingId };
}
