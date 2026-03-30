import { api } from '@/lib/api';

export async function uploadVendorDocument(vendorId: string, formData: FormData) {
  const { data } = await api.post(`/vendors/${vendorId}/documents`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000, // 2 min for large files
  });
  return data;
}

export async function deleteVendorDocument(vendorId: string, docId: string) {
  await api.delete(`/vendors/${vendorId}/documents/${docId}`);
}

export async function getVendorDocumentUrl(vendorId: string, docId: string): Promise<string> {
  const { data } = await api.get<{ url: string }>(`/vendors/${vendorId}/documents/${docId}/url`);
  return data.url;
}
