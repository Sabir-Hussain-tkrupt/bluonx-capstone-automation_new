import { useEffect, useMemo, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import {
  FileText,
  Flag,
  Folder,
  LayoutDashboard,
  LayoutTemplate,
  Settings,
  Users,
} from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { ROUTES } from '@/constants/routes';
import { Sidebar } from '@/components/ui/Sidebar';
import { TopHeader } from '@/components/ui/TopHeader';
import { UserMenuPanel, getInitials } from '@/components/ui/UserMenu';
import { Breadcrumbs } from '@/components/ui/Breadcrumbs';
import { NotificationBell } from '@/features/notifications/components/NotificationBell';
import { mainScrollRef } from '@/components/layout/mainScrollRef';
import { useBreadcrumbs } from '@/hooks/useBreadcrumbs';
import { usePausedMilestonesCount } from '@/features/dashboard/hooks/usePausedMilestones';
import type { SidebarSection } from '@/components/ui/Sidebar';
import bluonxLogo from '@/assets/bluonx-logo.png';

const SIDEBAR_COLLAPSED_KEY = 'bluonx:sidebar:collapsed';

export function DashboardLayout() {
  const location = useLocation();
  const { profile, signOut } = useAuth();
  const breadcrumbItems = useBreadcrumbs();
  const { data: pausedCount } = usePausedMilestonesCount();
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    const stored = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    if (stored !== null) return stored === 'true';
    return window.innerWidth < 1024;
  });
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        setSidebarCollapsed((c) => !c);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Close mobile sidebar on navigation — setState here is intentional:
  // we reset UI state in response to route changes (an external system).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- resetting UI on route change is a valid pattern
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
            icon: <LayoutDashboard className="h-5 w-5" aria-hidden="true" />,
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
            icon: <Users className="h-5 w-5" aria-hidden="true" />,
          },
          {
            id: 'projects',
            label: 'Projects',
            href: ROUTES.PROJECTS,
            icon: <Folder className="h-5 w-5" aria-hidden="true" />,
          },
          {
            id: 'milestones',
            label: 'Milestones',
            href: ROUTES.MILESTONES,
            icon: <Flag className="h-5 w-5" aria-hidden="true" />,
            badge: pausedCount,
          },
          {
            id: 'bids',
            label: 'Bids',
            href: ROUTES.BID_PACKAGES,
            icon: <FileText className="h-5 w-5" aria-hidden="true" />,
          },
          {
            id: 'bid-templates',
            label: 'Bid Templates',
            href: ROUTES.BID_TEMPLATES,
            icon: <LayoutTemplate className="h-5 w-5" aria-hidden="true" />,
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
            icon: <Settings className="h-5 w-5" aria-hidden="true" />,
            },
          ],
        });
    }

    return sections;
  }, [profile?.role, pausedCount]);

  // Derive display values from auth profile
  const userName = profile?.full_name || 'User';
  const userEmail = profile?.email || '';
  const userRole = profile?.role === 'admin' ? 'Admin' : 'Project Manager';

  return (
    <div className="flex h-screen overflow-hidden">
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
                <span className="text-xl font-bold text-white">BluOnX</span>
              </div>
            )
          }
          user={profile ? { name: userName, role: userRole, initials: getInitials(userName) } : undefined}
          userMenu={
            <UserMenuPanel
              userName={userName}
              userEmail={userEmail}
              onSignOut={signOut}
              anchor="top-right"
              onClose={() => {}}
            />
          }
        />
      </div>

      {/* Main content area */}
      <main className="flex flex-1 flex-col overflow-hidden bg-secondary-100">
        <TopHeader
          onMenuToggle={() => setMobileMenuOpen((o) => !o)}
          breadcrumbs={<Breadcrumbs items={breadcrumbItems} />}
          notificationBell={<NotificationBell />}
        />

        {/* Page content rendered by child routes — the app's only scroll region */}
        <div ref={mainScrollRef} className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
