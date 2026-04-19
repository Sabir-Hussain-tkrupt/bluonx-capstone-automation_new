/**
 * VendorPortalContext — holds the mock vendor JWT and full bid context.
 *
 * Scope: ONLY mounted under the /bid/* route subtree (see
 * frontend/src/routes/index.tsx). The admin dashboard never
 * instantiates this context, so there is zero bleed between portals.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';
import {
  setAuthFailureHandler,
  setVendorJwt as setApiJwt,
} from '../services/portalApi';
import type { VendorBidContext } from '../types/portal';

interface VendorPortalContextValue {
  jwt: string | null;
  bidContext: VendorBidContext | null;
  setSession: (jwt: string, bidContext: VendorBidContext) => void;
  clearSession: () => void;
}

const VendorPortalReactContext = createContext<VendorPortalContextValue | null>(null);

export function VendorPortalProvider({ children }: { children: ReactNode }) {
  const [jwt, setJwt] = useState<string | null>(null);
  const [bidContext, setBidContext] = useState<VendorBidContext | null>(null);
  const navigate = useNavigate();

  const setSession = useCallback((newJwt: string, newContext: VendorBidContext) => {
    setJwt(newJwt);
    setBidContext(newContext);
    setApiJwt(newJwt);
  }, []);

  const clearSession = useCallback(() => {
    setJwt(null);
    setBidContext(null);
    setApiJwt(null);
  }, []);

  // Any authenticated portal call that returns 401 means the vendor JWT
  // expired or was revoked mid-session. Clearing state + routing to
  // /bid/expired (where the user can re-click the magic link) lets the
  // backend remain the source of truth for session validity.
  useEffect(() => {
    setAuthFailureHandler(() => {
      clearSession();
      navigate(ROUTES.PORTAL_EXPIRED, { replace: true });
    });
    return () => setAuthFailureHandler(null);
  }, [navigate, clearSession]);

  const value = useMemo<VendorPortalContextValue>(
    () => ({ jwt, bidContext, setSession, clearSession }),
    [jwt, bidContext, setSession, clearSession],
  );

  return (
    <VendorPortalReactContext.Provider value={value}>
      {children}
    </VendorPortalReactContext.Provider>
  );
}

export function useVendorPortal(): VendorPortalContextValue {
  const ctx = useContext(VendorPortalReactContext);
  if (!ctx) {
    throw new Error('useVendorPortal must be used inside <VendorPortalProvider>');
  }
  return ctx;
}
