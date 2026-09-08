/**
 * VendorPortalContext — holds the vendor JWT and full bid context for
 * the active portal session (real or mocked, selected by VITE_DEMO_MODE).
 *
 * Scope: ONLY mounted under the /bid/* route subtree (see
 * frontend/src/routes/index.tsx). The admin dashboard never
 * instantiates this context, so there is zero bleed between portals.
 *
 * ── Persistence ─────────────────────────────────────────────────────
 * The JWT and bid_context are mirrored to sessionStorage so a page
 * refresh mid-form does not nuke the session. sessionStorage is
 * deliberate over localStorage: the JWT is short-lived (4h) and
 * tab-scoped — localStorage would leak it across "restore session"
 * browser features and other tabs. On mount we hydrate from storage,
 * but only after a local exp-claim sanity check; an expired or
 * malformed JWT is purged so the user lands on /bid/expired the next
 * time they hit a guarded route, instead of triggering a 401 round-trip.
 */

import {
  useCallback,
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
import type { VendorBidContext, VendorMilestoneContext } from '../types/portal';
import {
  VendorPortalReactContext,
  type VendorPortalContextValue,
} from './vendorPortalSession';

// ── sessionStorage keys ─────────────────────────────────────────────
// Namespaced to avoid collisions with any future per-tab storage.
const JWT_STORAGE_KEY = 'bluonx_vendor_jwt';
const BID_CONTEXT_STORAGE_KEY = 'bluonx_vendor_bid_context';
const MILESTONE_CONTEXT_STORAGE_KEY = 'bluonx_vendor_milestone_context';

// ── Storage helpers ─────────────────────────────────────────────────
// All sessionStorage access goes through these wrappers so a single
// try/catch handles the (rare) case where storage is unavailable —
// e.g. some privacy modes — without crashing the provider mount.

function safeGetItem(key: string): string | null {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSetItem(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    /* ignore — fall back to in-memory only */
  }
}

function safeRemoveItem(key: string): void {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

function clearStoredSession(): void {
  safeRemoveItem(JWT_STORAGE_KEY);
  safeRemoveItem(BID_CONTEXT_STORAGE_KEY);
  safeRemoveItem(MILESTONE_CONTEXT_STORAGE_KEY);
}

// ── JWT exp check (no signature verification) ───────────────────────
// The server is the only authoritative validator. This local check
// exists solely to avoid hydrating a JWT we already know is dead —
// otherwise we'd push the user into the form, fire one API call, get
// a 401, and only THEN redirect. Decoding the payload is a string-op,
// not a security boundary.

function decodeJwtPayload(jwt: string): { exp?: number } | null {
  const parts = jwt.split('.');
  if (parts.length !== 3) return null;

  // Base64url → base64, then pad to a multiple of 4.
  let b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
  const pad = b64.length % 4;
  if (pad === 2) b64 += '==';
  else if (pad === 3) b64 += '=';
  else if (pad !== 0) return null;

  try {
    const json = atob(b64);
    return JSON.parse(json) as { exp?: number };
  } catch {
    return null;
  }
}

function isJwtAlive(jwt: string): boolean {
  const payload = decodeJwtPayload(jwt);
  if (!payload || typeof payload.exp !== 'number') return false;
  // 5-second skew so a JWT that ticks over mid-hydration doesn't die
  // a beat too early relative to the server clock.
  const nowSec = Math.floor(Date.now() / 1000);
  return payload.exp - 5 > nowSec;
}

// ── Hydration ───────────────────────────────────────────────────────
// Returns the persisted session iff BOTH keys are present, the JWT is
// well-formed, and exp is in the future. Any failure purges storage
// so we never leave half-state behind.

interface SessionState {
  jwt: string | null;
  bidContext: VendorBidContext | null;
  milestoneContext: VendorMilestoneContext | null;
}

const EMPTY_SESSION: SessionState = {
  jwt: null,
  bidContext: null,
  milestoneContext: null,
};

function hydrateInitialState(): SessionState {
  const storedJwt = safeGetItem(JWT_STORAGE_KEY);
  const storedBid = safeGetItem(BID_CONTEXT_STORAGE_KEY);
  const storedMilestone = safeGetItem(MILESTONE_CONTEXT_STORAGE_KEY);
  // A session is exactly one KIND — bid XOR milestone.
  const storedContext = storedBid ?? storedMilestone;

  // Half-state (jwt or context missing) → purge and start fresh.
  if (!storedJwt || !storedContext) {
    if (storedJwt || storedContext) clearStoredSession();
    return EMPTY_SESSION;
  }

  if (!isJwtAlive(storedJwt)) {
    clearStoredSession();
    return EMPTY_SESSION;
  }

  try {
    const parsed = JSON.parse(storedContext);
    // Push the hydrated JWT into the Axios interceptor right away so the
    // first API call after a refresh already carries it. The lazy
    // initializer runs at most once per mount; setApiJwt is idempotent
    // so StrictMode's double-mount is harmless.
    setApiJwt(storedJwt);
    return storedBid
      ? { jwt: storedJwt, bidContext: parsed as VendorBidContext, milestoneContext: null }
      : { jwt: storedJwt, bidContext: null, milestoneContext: parsed as VendorMilestoneContext };
  } catch {
    clearStoredSession();
    return EMPTY_SESSION;
  }
}

export function VendorPortalProvider({ children }: { children: ReactNode }) {
  const [session, setSessionState] = useState<SessionState>(hydrateInitialState);
  const { jwt, bidContext, milestoneContext } = session;
  const navigate = useNavigate();

  const setSession = useCallback((newJwt: string, newContext: VendorBidContext) => {
    setSessionState({ jwt: newJwt, bidContext: newContext, milestoneContext: null });
    setApiJwt(newJwt);
    safeSetItem(JWT_STORAGE_KEY, newJwt);
    safeRemoveItem(MILESTONE_CONTEXT_STORAGE_KEY);
    safeSetItem(BID_CONTEXT_STORAGE_KEY, JSON.stringify(newContext));
  }, []);

  const setMilestoneSession = useCallback(
    (newJwt: string, newContext: VendorMilestoneContext) => {
      setSessionState({ jwt: newJwt, bidContext: null, milestoneContext: newContext });
      setApiJwt(newJwt);
      safeSetItem(JWT_STORAGE_KEY, newJwt);
      safeRemoveItem(BID_CONTEXT_STORAGE_KEY);
      safeSetItem(MILESTONE_CONTEXT_STORAGE_KEY, JSON.stringify(newContext));
    },
    [],
  );

  const clearSession = useCallback(() => {
    setSessionState(EMPTY_SESSION);
    setApiJwt(null);
    clearStoredSession();
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
    () => ({
      jwt,
      bidContext,
      milestoneContext,
      setSession,
      setMilestoneSession,
      clearSession,
    }),
    [jwt, bidContext, milestoneContext, setSession, setMilestoneSession, clearSession],
  );

  return (
    <VendorPortalReactContext.Provider value={value}>
      {children}
    </VendorPortalReactContext.Provider>
  );
}
