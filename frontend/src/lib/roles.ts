import { useAuth } from '@/contexts/AuthContext';
import type { AppRole, UserProfile } from '@/types/auth.types';

/**
 * Role checks for the financial module.
 *
 * Mirrors `user_has_any_role` in backend/app/core/auth.py: admins pass every
 * check; otherwise the user needs at least one of the roles, from users.role or
 * user_roles. These only decide what the UI SHOWS — the backend check is the
 * real gate, so a hidden button is never the only protection.
 */
export function hasAnyRole(
  profile: Pick<UserProfile, 'role' | 'roles'> | null | undefined,
  ...roles: AppRole[]
): boolean {
  if (!profile) return false;
  const held = new Set<AppRole>([profile.role, ...(profile.roles ?? [])]);
  if (held.has('admin')) return true;
  return roles.some((r) => held.has(r));
}

/** Convenience hook: `const canUpload = useHasRole('field_manager', 'finance')`. */
export function useHasRole(...roles: AppRole[]): boolean {
  const { profile } = useAuth();
  return hasAnyRole(profile, ...roles);
}

/** Display labels for every role. */
export const ROLE_LABELS: Record<AppRole, string> = {
  admin: 'Admin',
  project_manager: 'Project Manager',
  field_manager: 'Field Manager',
  executive: 'Executive',
  finance: 'Finance',
};

/** Roles an admin grants on top of the base role. */
export const FINANCIAL_ROLES: { value: Exclude<AppRole, 'admin' | 'project_manager'>; label: string; description: string }[] = [
  { value: 'field_manager', label: 'Field Manager', description: 'Confirms work in the field, creates variances, uploads invoices.' },
  { value: 'executive', label: 'Executive', description: 'Approves contingency top-ups and large payments; sees the owner dashboard.' },
  { value: 'finance', label: 'Finance', description: 'Receives payment hand-offs, sees invoices and cash flow, closes months.' },
];
