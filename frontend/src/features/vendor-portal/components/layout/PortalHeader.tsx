import bluonxLogo from '@/assets/bluonx-logo.png';
import { useVendorPortal } from '../../context/VendorPortalContext';

export function PortalHeader() {
  const { bidContext } = useVendorPortal();

  return (
    <header className="sticky top-0 z-10 border-b border-secondary-200 bg-white shadow-sm">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6 sm:py-4">
        {/* Brand */}
        <div className="flex items-center gap-2">
          <img src={bluonxLogo} alt="" className="h-9 w-9" />
          <div className="leading-tight">
            <p className="text-sm font-semibold text-primary-600">BluOnX</p>
            <p className="text-[11px] font-medium tracking-wide text-secondary-500 uppercase">
              Vendor Bid Portal
            </p>
          </div>
        </div>

        {/* Project / vendor context — only renders after magic-link lands */}
        {bidContext && (
          <div className="hidden min-w-0 flex-1 text-right sm:block">
            <p className="truncate text-sm font-semibold text-secondary-900">
              {bidContext.project.name}
            </p>
            <p className="truncate text-xs text-secondary-500">
              {bidContext.vendor.company_name} · {bidContext.task.name}
            </p>
          </div>
        )}
      </div>

      {/* Compact mobile second row */}
      {bidContext && (
        <div className="border-t border-secondary-100 bg-secondary-50 px-4 py-2 sm:hidden">
          <p className="truncate text-[13px] font-semibold text-secondary-900">
            {bidContext.project.name}
          </p>
          <p className="truncate text-xs text-secondary-500">
            {bidContext.vendor.company_name}
          </p>
        </div>
      )}
    </header>
  );
}
