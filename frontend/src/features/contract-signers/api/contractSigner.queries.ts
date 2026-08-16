import { supabase } from '@/lib/supabase';
import { fromSupabaseError } from '@/lib/api';
import type { ContractSigner } from '../types';

/**
 * The full signer roster, read direct via Supabase.
 *
 * There is deliberately no FastAPI GET: `contract_signers_select_authenticated`
 * already permits any active user to read every row including inactive ones, and
 * nothing about a signer is server-computed. A second read path would be two
 * places to keep in sync for no gain.
 */
export async function fetchContractSigners(): Promise<ContractSigner[]> {
  const { data, error } = await supabase
    .from('contract_signers')
    .select('*')
    .order('is_active', { ascending: false })
    .order('full_name');

  if (error) throw fromSupabaseError(error);

  return (data ?? []) as unknown as ContractSigner[];
}

/** Only the signers a PM may currently choose from on the award screen. */
export async function fetchActiveContractSigners(): Promise<ContractSigner[]> {
  const { data, error } = await supabase
    .from('contract_signers')
    .select('*')
    .eq('is_active', true)
    .order('full_name');

  if (error) throw fromSupabaseError(error);

  return (data ?? []) as unknown as ContractSigner[];
}
