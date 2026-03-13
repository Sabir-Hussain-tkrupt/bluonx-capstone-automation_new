import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { importVendorsCSV } from '@/features/vendors/api/vendor.mutations';
import type { VendorImportRow } from '@/features/vendors/api/vendor.mutations';

export function useImportVendors() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (rows: VendorImportRow[]) => importVendorsCSV(rows),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.vendors.all });
    },
  });
}
