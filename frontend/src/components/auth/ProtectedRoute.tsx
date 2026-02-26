import { useAuth } from '@/contexts/AuthContext';
import { Navigate, useLocation } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';

interface ProtectedRouteProps {
  children: React.ReactNode;
  /** Optional: restrict to specific role. If not set, any authenticated user can access. */
  requiredRole?: 'admin' | 'project_manager';
}

/**
 * Wraps routes that require authentication.
 *
 * Usage:
 *
 *   <Route path="/dashboard" element={
 *     <ProtectedRoute>
 *       <DashboardLayout />
 *     </ProtectedRoute>
 *   } />
 *
 *   <Route path="/settings" element={
 *     <ProtectedRoute requiredRole="admin">
 *       <SettingsPage />
 *     </ProtectedRoute>
 *   } />
 */
export function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, profile } = useAuth();
  const location = useLocation();

  // 1. Still checking session — show nothing (prevents flash of login page)
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-gray-500">Loading...</p>
        {/* Replace with a proper spinner component in Task 2.5 */}
      </div>
    );
  }

  // 2. Not authenticated — redirect to login (preserves intended destination)
  if (!isAuthenticated) {
    return <Navigate to={ROUTES.LOGIN} state={{ from: location }} replace />;
  }

  // 3. Authenticated but wrong role — silently redirect to dashboard
  //    (don't reveal which role is required — prevents information leakage)
  if (requiredRole && profile?.role !== requiredRole) {
    return <Navigate to={ROUTES.DASHBOARD} replace />;
  }

  // 4. All good — render the protected content
  return <>{children}</>;
}
