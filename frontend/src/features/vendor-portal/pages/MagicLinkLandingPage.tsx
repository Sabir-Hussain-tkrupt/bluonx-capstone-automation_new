import { useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { ROUTES } from '@/constants/routes';
import { useVendorPortal } from '../context/VendorPortalContext';
import { validateToken } from '../services/portalApi';
import { PortalApiError } from '../types/portal';

export function MagicLinkLandingPage() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { setSession } = useVendorPortal();
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
        const response = await validateToken(token);
        setSession(response.jwt, response.bid_context);
        // Revision tokens get an interstitial landing screen; the
        // initial-bid path is unchanged.
        navigate(
          response.bid_context.revision_context
            ? ROUTES.PORTAL_REVISION
            : ROUTES.PORTAL_FORM,
          { replace: true },
        );
      } catch (err) {
        if (err instanceof PortalApiError) {
          switch (err.code) {
            case 'TOKEN_EXPIRED':
              navigate(ROUTES.PORTAL_EXPIRED, { replace: true });
              return;
            case 'BIDDING_CLOSED':
              navigate(ROUTES.PORTAL_CLOSED, { replace: true });
              return;
            case 'ALREADY_SUBMITTED':
              navigate(ROUTES.PORTAL_ALREADY_SUBMITTED, { replace: true });
              return;
            case 'TOKEN_INVALID':
            default:
              navigate(ROUTES.PORTAL_INVALID, { replace: true });
              return;
          }
        }
        navigate(ROUTES.PORTAL_INVALID, { replace: true });
      }
    })();
  }, [token, navigate, setSession]);

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
        Verifying your bid link
      </h1>
      <p className="mt-2 text-sm text-secondary-600">
        Hang tight — this should only take a moment.
      </p>
    </div>
  );
}
