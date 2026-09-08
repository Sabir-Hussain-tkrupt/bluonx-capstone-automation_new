import { useContext } from 'react';
import {
  VendorPortalReactContext,
  type VendorPortalContextValue,
} from './vendorPortalSession';

/**
 * Read the active vendor portal session. Throws outside the provider rather
 * than handing back a null session, so a component mounted on the wrong route
 * tree fails loudly instead of silently rendering as a logged-out vendor.
 */
export function useVendorPortal(): VendorPortalContextValue {
  const ctx = useContext(VendorPortalReactContext);
  if (!ctx) {
    throw new Error('useVendorPortal must be used inside <VendorPortalProvider>');
  }
  return ctx;
}
