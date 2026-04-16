import { useVendorPortal } from '../context/VendorPortalContext';
import type { VendorBidContext } from '../types/portal';

/**
 * Ergonomic read-only hook for components that can assume bid context
 * is loaded (anything inside VendorPortalGuard). Throws loudly if
 * misused, so missing-context bugs surface in dev immediately.
 */
export function useBidContext(): VendorBidContext {
  const { bidContext } = useVendorPortal();
  if (!bidContext) {
    throw new Error(
      'useBidContext called without bid context — component should be wrapped in VendorPortalGuard',
    );
  }
  return bidContext;
}
