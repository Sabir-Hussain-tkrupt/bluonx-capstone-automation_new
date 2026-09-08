/**
 * The React context object behind the vendor portal session, and its value
 * type.
 *
 * Split out of VendorPortalContext.tsx so that file exports only the provider
 * component: mixing value exports with a component export drops the module out
 * of Vite's Fast Refresh, so editing the provider full-reloads the page and
 * discards the vendor's in-progress bid form.
 *
 * Named "session" rather than "context" because a lowercase vendorPortalContext
 * would collide with VendorPortalContext.tsx on a case-insensitive filesystem.
 */
import { createContext } from 'react';
import type { VendorBidContext, VendorMilestoneContext } from '../types/portal';

export interface VendorPortalContextValue {
  jwt: string | null;
  bidContext: VendorBidContext | null;
  milestoneContext: VendorMilestoneContext | null;
  setSession: (jwt: string, bidContext: VendorBidContext) => void;
  setMilestoneSession: (
    jwt: string,
    milestoneContext: VendorMilestoneContext,
  ) => void;
  clearSession: () => void;
}

export const VendorPortalReactContext =
  createContext<VendorPortalContextValue | null>(null);
