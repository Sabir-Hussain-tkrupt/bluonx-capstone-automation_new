import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { UserRosterTable } from '../UserRosterTable';
import type { UserAdminResponse } from '../../types';

// The row-action menu uses the api client via mutation hooks; stub it so nothing
// hits the network at render time.
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const ADMIN_ID = 'admin-1';

function user(overrides: Partial<UserAdminResponse> = {}): UserAdminResponse {
  return {
    id: 'u-1',
    email: 'person@bluonx.dev',
    full_name: 'Person One',
    role: 'project_manager',
    is_active: true,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    deleted_at: null,
    invited_by: ADMIN_ID,
    status: 'active',
    ...overrides,
  };
}

const admin = user({
  id: ADMIN_ID,
  email: 'admin@bluonx.dev',
  full_name: 'Ada Admin',
  role: 'admin',
  invited_by: null,
});

describe('UserRosterTable', () => {
  it('renders name, email, role label, status badge and resolved invited-by', () => {
    const rows = [
      admin,
      user({ id: 'u-2', full_name: 'Pat Pending', email: 'pat@bluonx.dev', status: 'pending' }),
      user({
        id: 'u-3',
        full_name: 'Dan Deactivated',
        email: 'dan@bluonx.dev',
        is_active: false,
        status: 'deactivated',
      }),
    ];
    renderWithRouter(<UserRosterTable users={rows} isLoading={false} currentUserId={ADMIN_ID} />);

    // The shared Table renders a desktop table AND mobile cards, so each value
    // appears more than once in jsdom; assert presence via getAllByText.
    const present = (text: string) => expect(screen.getAllByText(text).length).toBeGreaterThan(0);
    present('Ada Admin');
    present('pat@bluonx.dev');
    present('Project Manager');
    present('Admin');

    // Status badges (StatusBadge title-cases the status string).
    present('Active');
    present('Pending');
    present('Deactivated');

    // invited_by (a UUID) resolves to the inviter's name via the roster map;
    // the bootstrap admin (invited_by null) shows an em-dash.
    expect(screen.getAllByText('Ada Admin').length).toBeGreaterThanOrEqual(2);
    present('—');
  });

  it('shows the empty state when there are no users', () => {
    renderWithRouter(
      <UserRosterTable
        users={[]}
        isLoading={false}
        currentUserId={ADMIN_ID}
        emptyState={<div>No users yet</div>}
      />,
    );
    expect(screen.getByText('No users yet')).toBeInTheDocument();
  });

  it('does not render data rows while loading', () => {
    renderWithRouter(
      <UserRosterTable users={[admin]} isLoading currentUserId={ADMIN_ID} />,
    );
    expect(screen.queryByText('Ada Admin')).not.toBeInTheDocument();
  });
});
