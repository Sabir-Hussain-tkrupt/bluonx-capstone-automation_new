import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { UserManagementPage } from '../UserManagementPage';
import type { UserAdminResponse } from '../../types';
import { makeApiError } from '@/test/api-error';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ profile: { id: 'admin-1', role: 'admin', full_name: 'Ada Admin' } }),
}));

const mockUseUsers = vi.fn();
vi.mock('../../hooks/useUsers', () => ({
  useUsers: () => mockUseUsers(),
}));

function row(overrides: Partial<UserAdminResponse> = {}): UserAdminResponse {
  return {
    id: 'admin-1',
    email: 'admin@bluonx.dev',
    full_name: 'Ada Admin',
    role: 'admin',
    is_active: true,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    deleted_at: null,
    invited_by: null,
    status: 'active',
    ...overrides,
  };
}

describe('UserManagementPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the roster and the invite button', () => {
    mockUseUsers.mockReturnValue({ data: [row()], isLoading: false, isError: false });
    renderWithRouter(<UserManagementPage />);

    expect(screen.getByRole('button', { name: /invite user/i })).toBeInTheDocument();
    // Table renders desktop + mobile views, so the value appears more than once.
    expect(screen.getAllByText('admin@bluonx.dev').length).toBeGreaterThan(0);
  });

  it('renders the empty state when there are no users', () => {
    mockUseUsers.mockReturnValue({ data: [], isLoading: false, isError: false });
    renderWithRouter(<UserManagementPage />);

    expect(screen.getByText(/no users yet/i)).toBeInTheDocument();
  });

  it('surfaces a load error via errorMessage', () => {
    mockUseUsers.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: makeApiError('boom', 500),
      refetch: vi.fn(),
    });
    renderWithRouter(<UserManagementPage />);

    expect(screen.getByText(/could not load users/i)).toBeInTheDocument();
    expect(screen.getByText('boom')).toBeInTheDocument();
  });

  it('does not render rows while loading', () => {
    mockUseUsers.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    renderWithRouter(<UserManagementPage />);

    expect(screen.queryByText('admin@bluonx.dev')).not.toBeInTheDocument();
  });
});
