import { Outlet } from 'react-router-dom';
import { PortalHeader } from './PortalHeader';
import { PortalFooter } from './PortalFooter';

export function PortalLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-secondary-50">
      <PortalHeader />
      <main id="portal-main" className="flex-1">
        <Outlet />
      </main>
      <PortalFooter />
    </div>
  );
}
