import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from '../ProtectedRoute';

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

function renderAt(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route
          path="/settings/users"
          element={
            <ProtectedRoute requiredRole="admin">
              <div>USER MANAGEMENT PAGE</div>
            </ProtectedRoute>
          }
        />
        <Route path="/dashboard" element={<div>DASHBOARD</div>} />
        <Route path="/login" element={<div>LOGIN</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProtectedRoute (admin-only route)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('redirects a project_manager away from an admin route (C3)', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      profile: { role: 'project_manager' },
    });
    renderAt('/settings/users');

    expect(screen.queryByText('USER MANAGEMENT PAGE')).not.toBeInTheDocument();
    expect(screen.getByText('DASHBOARD')).toBeInTheDocument();
  });

  it('renders the admin route content for an admin', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      isLoading: false,
      profile: { role: 'admin' },
    });
    renderAt('/settings/users');

    expect(screen.getByText('USER MANAGEMENT PAGE')).toBeInTheDocument();
  });

  it('redirects an unauthenticated user to login', () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false, isLoading: false, profile: null });
    renderAt('/settings/users');

    expect(screen.getByText('LOGIN')).toBeInTheDocument();
  });
});
