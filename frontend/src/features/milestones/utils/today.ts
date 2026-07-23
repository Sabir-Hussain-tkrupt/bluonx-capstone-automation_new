/** Local calendar date as YYYY-MM-DD, for `min` on date pickers.
 *
 * A soft UX guard so the picker discourages past dates; the backend
 * `business_today()` (America/Chicago) check is the authoritative rule, and a
 * browser-timezone edge that slips past this surfaces the backend's message. */
export function todayStr(): string {
  return new Date().toLocaleDateString('en-CA');
}
