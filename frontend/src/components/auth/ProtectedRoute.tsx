import { useAuth } from '@/contexts/AuthContext';
// import { Navigate, useLocation } from 'react-router-dom';  // Task 2.2

interface ProtectedRouteProps {
  children: React.ReactNode;
  /** Optional: restrict to specific role. If not set, any authenticated user can access. */
  requiredRole?: 'admin' | 'project_manager';
}

/**
 * Wraps routes that require authentication.
 *
 * Usage (in Task 2.2 when routing is set up):
 *
 *   <Route path="/dashboard" element={
 *     <ProtectedRoute>
 *       <DashboardLayout />
 *     </ProtectedRoute>
 *   } />
 *
 *   <Route path="/admin/users" element={
 *     <ProtectedRoute requiredRole="admin">
 *       <UserManagement />
 *     </ProtectedRoute>
 *   } />
 */
export function ProtectedRoute({ children, requiredRole }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, profile } = useAuth();
  // const location = useLocation();  // Task 2.2

  // 1. Still checking session — show nothing (prevents flash of login page)
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-gray-500">Loading...</p>
        {/* Replace with a proper spinner component in Task 2.5 */}
      </div>
    );
  }

  // 2. Not authenticated — redirect to login
  if (!isAuthenticated) {
    // Task 2.2: Replace with Navigate component
    // return <Navigate to="/login" state={{ from: location }} replace />;
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-red-500">Not authenticated. Login page will be built in Task 2.7.</p>
      </div>
    );
  }

  // 3. Authenticated but wrong role — show unauthorized
  if (requiredRole && profile?.role !== requiredRole) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-red-500">
          Unauthorized. This page requires the "{requiredRole}" role.
        </p>
      </div>
    );
  }

  // 4. All good — render the protected content
  return <>{children}</>;
}