/**
 * VendorPortalGuard — route guard for the /bid/form and /bid/submitted
 * branches. If no mock bid context is present, redirect to the invalid-
 * token page. In real-world usage (Task 5.2) the vendor will click the
 * magic link again to re-issue a JWT.
 */

import { Navigate, Outlet } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';
import { useVendorPortal } from './VendorPortalContext';

export function VendorPortalGuard() {
  const { jwt, bidContext } = useVendorPortal();

  if (!jwt || !bidContext) {
    return <Navigate to={ROUTES.PORTAL_INVALID} replace />;
  }

  return <Outlet />;
}
