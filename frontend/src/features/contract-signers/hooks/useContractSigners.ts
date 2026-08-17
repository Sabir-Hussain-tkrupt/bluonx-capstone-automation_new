import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import {
  fetchActiveContractSigners,
  fetchContractSigners,
} from '../api/contractSigner.queries';

/** The whole roster, inactive rows included — the settings table view. */
export function useContractSigners() {
  return useQuery({
    queryKey: queryKeys.contractSigners.lists(),
    queryFn: fetchContractSigners,
    staleTime: 30_000,
  });
}

/**
 * Only active signers — the award-screen dropdown. Kept as a separate key so the
 * PM's dropdown is not served the settings page's cache of revoked entries.
 */
export function useActiveContractSigners(enabled = true) {
  return useQuery({
    queryKey: queryKeys.contractSigners.list({ isActive: true }),
    queryFn: fetchActiveContractSigners,
    staleTime: 30_000,
    enabled,
  });
}
