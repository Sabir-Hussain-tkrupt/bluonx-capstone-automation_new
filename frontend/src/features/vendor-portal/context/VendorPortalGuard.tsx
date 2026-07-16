/**
 * VendorPortalGuard — route guard for the /bid/form and /bid/submitted
 * branches. If no vendor JWT + bid context are loaded in the portal
 * context, the session either expired, was cleared, or the user
 * navigated directly to a guarded URL without going through the magic
 * link first. In every case the right recovery is the same: send them
 * to /bid/expired, where the copy tells them to click the magic link
 * again to re-issue a JWT.
 *
 * "Invalid" is reserved for token validation failures (404 from
 * /validate-token) — not for unauthenticated access to portal routes.
 */

import { Navigate, Outlet } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';
import { useVendorPortal } from './VendorPortalContext';

export function VendorPortalGuard() {
  const { jwt, bidContext, milestoneContext } = useVendorPortal();

  // A live session is a JWT plus exactly one kind of context (bid or milestone).
  if (!jwt || (!bidContext && !milestoneContext)) {
    return <Navigate to={ROUTES.PORTAL_EXPIRED} replace />;
  }

  return <Outlet />;
}
