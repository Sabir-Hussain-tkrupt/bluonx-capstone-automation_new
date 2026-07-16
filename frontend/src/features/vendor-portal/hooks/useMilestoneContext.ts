import { useVendorPortal } from '../context/VendorPortalContext';
import type { VendorMilestoneContext } from '../types/portal';

/**
 * Ergonomic read-only hook for milestone check-in pages that can assume a
 * milestone session is loaded (anything inside VendorPortalGuard reached via
 * the milestone landing). Throws loudly if misused, so a missing-context bug
 * surfaces in dev immediately — mirrors useBidContext.
 */
export function useMilestoneContext(): VendorMilestoneContext {
  const { milestoneContext } = useVendorPortal();
  if (!milestoneContext) {
    throw new Error(
      'useMilestoneContext called without milestone context — component should be wrapped in VendorPortalGuard and reached via the milestone landing',
    );
  }
  return milestoneContext;
}
