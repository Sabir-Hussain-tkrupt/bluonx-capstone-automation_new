import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { ROUTES } from '@/constants/routes';
import { Sidebar } from '@/components/ui/Sidebar';
import { TopHeader } from '@/components/ui/TopHeader';
import { UserMenu } from '@/components/ui/UserMenu';
import { Breadcrumbs } from '@/components/ui/Breadcrumbs';
import { useBreadcrumbs } from '@/hooks/useBreadcrumbs';
import type { SidebarSection } from '@/components/ui/Sidebar';
import bluonxLogo from '@/assets/bluonx-logo.png';

function NavIcon({ d }: { d: string }) {
  return (
    <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d={d} clipRule="evenodd" />
    </svg>
  );
}

export function DashboardLayout() {
  const location = useLocation();
  const { profile, signOut } = useAuth();
  const breadcrumbItems = useBreadcrumbs();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Close mobile sidebar on navigation
  useEffect(() => {
    setMobileMenuOpen(false);
  }, [location.pathname]);

  // Role-based sidebar sections
  const sidebarSections = useMemo<SidebarSection[]>(() => {
    const sections: SidebarSection[] = [
      {
        items: [
          {
            id: 'dashboard',
            label: 'Dashboard',
            href: ROUTES.DASHBOARD,
            icon: <NavIcon d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z" />,
          },
        ],
      },
      {
        title: 'Management',
        items: [
          {
            id: 'vendors',
            label: 'Vendors',
            href: ROUTES.VENDORS,
            icon: <NavIcon d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z" />,
          },
          {
            id: 'projects',
            label: 'Projects',
            href: ROUTES.PROJECTS,
            icon: <NavIcon d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />,
          },
        ],
      },
    ];

    // Admin-only section
    if (profile?.role === 'admin') {
      sections.push({
        title: 'Admin',
        items: [
          {
            id: 'settings',
            label: 'Settings',
            href: ROUTES.SETTINGS,
            icon: <NavIcon d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" />,
            },
          ],
        });
    }

    return sections;
  }, [profile?.role]);

  // Derive display values from auth profile
  const userName = profile?.full_name || 'User';
  const userEmail = profile?.email || '';
  const userRole = profile?.role === 'admin' ? 'Admin' : 'Project Manager';

  return (
    <div className="flex min-h-screen">
      {/* Mobile sidebar overlay */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar — hidden on mobile, visible on lg+ */}
      <div
        className={`
          fixed inset-y-0 left-0 z-50 lg:static lg:z-auto
          ${mobileMenuOpen ? 'block' : 'hidden lg:block'}
        `}
      >
        <Sidebar
          sections={sidebarSections}
          currentPath={location.pathname}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
          logo={
            sidebarCollapsed ? (
              <img src={bluonxLogo} alt="BluOnX" className="h-7 w-7" />
            ) : (
              <div className="flex items-center gap-2">
                <img src={bluonxLogo} alt="" className="h-8 w-8" />
                <span className="text-xl font-bold text-primary-600">BluOnX</span>
              </div>
            )
          }
        />
      </div>

      {/* Main content area */}
      <main className="flex-1 bg-secondary-50">
        <TopHeader
          onMenuToggle={() => setMobileMenuOpen((o) => !o)}
          breadcrumbs={<Breadcrumbs items={breadcrumbItems} />}
          userMenu={
            <UserMenu
              userName={userName}
              userEmail={userEmail}
              userRole={userRole}
              onSignOut={signOut}
            />
          }
        />

        {/* Page content rendered by child routes */}
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
