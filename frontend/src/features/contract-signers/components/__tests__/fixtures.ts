/**
 * The one row builder for the contract-signers tests.
 *
 * Deliberately shared rather than redeclared per file: the user-management suite
 * grew three near-identical local builders that drifted, and this feature does
 * not repeat that.
 */
import type { ContractSigner } from '../../types';

export function signer(overrides: Partial<ContractSigner> = {}): ContractSigner {
  return {
    id: 'cs-1',
    full_name: 'Dana Reyes',
    email: 'dana@bluonx.dev',
    title: 'VP of Development',
    is_active: true,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...overrides,
  };
}
