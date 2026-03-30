import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
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
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const download = async (vendorId: string, docId: string) => {
    setDownloadingId(docId);
    try {
      const url = await getVendorDocumentUrl(vendorId, docId);
      window.open(url, '_blank');
    } finally {
      setDownloadingId(null);
    }
  };

  return { download, downloadingId };
}
