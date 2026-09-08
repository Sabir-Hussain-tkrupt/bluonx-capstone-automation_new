import { useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { ROUTES } from '@/constants/routes';
import { useVendorPortal } from '../context/useVendorPortal';
import { validateMilestoneToken } from '../services/portalApi';
import { PortalApiError } from '../types/portal';

/**
 * Entry point for a milestone check-in magic link (`/milestone/:token`).
 * Validates the token, then routes by outcome:
 *   - actionable       → store the session, go to the Yes/No page
 *   - already_answered → the "recorded" page (carrying the prior answer)
 *   - 410 (stale/terminal) → "no longer current"
 *   - 404 (unknown)        → the shared invalid-link page
 * Runs before any session exists, so it lives OUTSIDE VendorPortalGuard.
 */
export function MilestoneLandingPage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { setMilestoneSession } = useVendorPortal();
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    if (!token) {
      navigate(ROUTES.PORTAL_INVALID, { replace: true });
      return;
    }

    (async () => {
      try {
        const res = await validateMilestoneToken(token);
        if (res.outcome === 'already_answered') {
          navigate(ROUTES.PORTAL_MILESTONE_RECORDED, {
            replace: true,
            state: {
              recorded_value: res.recorded_value,
              recorded_at: res.recorded_at,
            },
          });
          return;
        }
        // actionable — a JWT and context are guaranteed present.
        if (res.jwt && res.milestone_context) {
          setMilestoneSession(res.jwt, res.milestone_context);
          navigate(ROUTES.PORTAL_MILESTONE, { replace: true });
          return;
        }
        navigate(ROUTES.PORTAL_INVALID, { replace: true });
      } catch (err) {
        if (err instanceof PortalApiError) {
          // 410 = stale cycle / terminal milestone; 404 = unknown link.
          if (err.status === 410) {
            navigate(ROUTES.PORTAL_MILESTONE_INACTIVE, { replace: true });
            return;
          }
        }
        navigate(ROUTES.PORTAL_INVALID, { replace: true });
      }
    })();
  }, [token, navigate, setMilestoneSession]);

  return (
    <div className="mx-auto flex max-w-lg flex-col items-center justify-center px-4 py-16 text-center">
      <div
        role="status"
        aria-live="polite"
        className="flex h-16 w-16 items-center justify-center rounded-full border-4 border-primary-100"
      >
        <Loader2 className="h-8 w-8 animate-spin text-primary-600" aria-hidden="true" />
      </div>
      <h1 className="mt-6 text-xl font-semibold text-secondary-900">
        Opening your check-in
      </h1>
      <p className="mt-2 text-sm text-secondary-600">
        Hang tight — this should only take a moment.
      </p>
    </div>
  );
}
