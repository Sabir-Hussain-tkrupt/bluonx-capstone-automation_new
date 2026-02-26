import { useAuth } from '@/contexts/AuthContext';
import { Navigate } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';

interface PublicRouteProps {
  children: React.ReactNode;
}

/**
 * Wraps routes that should only be accessible to unauthenticated users.
 * Authenticated users are redirected to the dashboard.
 *
 * Usage:
 *
 *   <Route element={<PublicRoute><AuthLayout /></PublicRoute>}>
 *     <Route path="/login" element={<LoginPage />} />
 *   </Route>
 */
export function PublicRoute({ children }: PublicRouteProps) {
  const { isAuthenticated, isLoading } = useAuth();

  // Still checking session — show loading (same as ProtectedRoute)
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  // Already authenticated — redirect away from auth pages
  if (isAuthenticated) {
    return <Navigate to={ROUTES.DASHBOARD} replace />;
  }

  // Not authenticated — render the auth page
  return <>{children}</>;
}
