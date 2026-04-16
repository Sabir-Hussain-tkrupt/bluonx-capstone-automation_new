/**
 * Renders a thin amber banner at the very top of the portal layout
 * whenever `VITE_DEMO_MODE=true`, so nobody mistakes a mocked demo
 * run for a real submission. Rendered inside `PortalLayout` above
 * `PortalHeader`, so it covers every portal page.
 */
export function DemoModeBanner() {
  if (import.meta.env.VITE_DEMO_MODE !== 'true') return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="w-full border-b border-amber-300 bg-amber-100 px-4 py-1.5 text-center text-xs font-medium text-amber-900 sm:text-sm"
    >
      <span className="hidden sm:inline">
        Demo Mode — using mock data. Backend integration in progress.
      </span>
      <span className="sm:hidden">Demo Mode — mock data</span>
    </div>
  );
}
