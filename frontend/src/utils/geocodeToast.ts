import type { ToastData } from '@/components/ui/Toast/Toast';

type ToastFn = (options: Omit<ToastData, 'id'>) => void;

/**
 * Follow a successful save with a warning when the server could not resolve
 * the address to coordinates.
 *
 * Deliberately a second toast rather than a changed success message: the write
 * DID succeed, and saying otherwise would send the user back to re-check work
 * that is fine. Without this the failure is invisible until someone notices
 * the record missing from a distance-filtered vendor search weeks later.
 */
export function notifyGeocodeWarning(
  toast: ToastFn,
  result: { geocode_warning?: string | null } | undefined | null,
): void {
  if (result?.geocode_warning) {
    toast({ variant: 'warning', message: result.geocode_warning });
  }
}
