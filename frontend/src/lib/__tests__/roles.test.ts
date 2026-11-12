import { describe, expect, it } from 'vitest';
import { hasAnyRole } from '../roles';

describe('hasAnyRole', () => {
  it('admins pass every check', () => {
    expect(hasAnyRole({ role: 'admin' }, 'finance')).toBe(true);
  });

  it('uses financial roles from user_roles', () => {
    const fm = { role: 'project_manager' as const, roles: ['field_manager' as const, 'project_manager' as const] };
    expect(hasAnyRole(fm, 'field_manager')).toBe(true);
    expect(hasAnyRole(fm, 'executive', 'finance')).toBe(false);
  });

  it('counts the base role and works without a roles list', () => {
    expect(hasAnyRole({ role: 'project_manager' }, 'project_manager')).toBe(true);
    expect(hasAnyRole({ role: 'project_manager' }, 'finance')).toBe(false);
  });

  it('is false without a profile', () => {
    expect(hasAnyRole(null, 'admin')).toBe(false);
  });
});
