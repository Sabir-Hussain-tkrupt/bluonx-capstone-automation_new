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
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { setVendorJwt as setApiJwt } from '../services/portalApi';
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
