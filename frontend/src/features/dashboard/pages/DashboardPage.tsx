import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { ROUTES } from '@/constants/routes';
import { supabase } from '@/lib/supabase';
import { useDashboardCounts } from '@/features/dashboard/hooks/useDashboardCounts';

function VendorsIcon() {
  return (
    <svg className="h-6 w-6" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z" />
    </svg>
  );
}

function ProjectsIcon() {
  return (
    <svg className="h-6 w-6" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
    </svg>
  );
}

function SettingsIcon() {
  return (
    <svg className="h-6 w-6" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
      <path fillRule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
    </svg>
  );
}

interface QuickNavCard {
  title: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  adminOnly?: boolean;
}

const QUICK_NAV_CARDS: QuickNavCard[] = [
  {
    title: 'Vendors',
    description: 'Manage vendor profiles, contacts, and trade certifications.',
    href: ROUTES.VENDORS,
    icon: <VendorsIcon />,
  },
  {
    title: 'Projects',
    description: 'View and manage development and construction projects.',
    href: ROUTES.PROJECTS,
    icon: <ProjectsIcon />,
  },
  {
    title: 'Settings',
    description: 'Manage users, trades, and system configuration.',
    href: ROUTES.SETTINGS,
    icon: <SettingsIcon />,
    adminOnly: true,
  },
];

interface StatPlaceholderProps {
  label: string;
  value: string;
  isLoading?: boolean;
}

function StatPlaceholder({ label, value, isLoading = false }: StatPlaceholderProps) {
  return (
    <div className="rounded-lg border border-secondary-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-secondary-500">{label}</p>
      {isLoading ? (
        <div className="mt-2 h-9 w-16 animate-pulse rounded bg-secondary-200" aria-hidden="true" />
      ) : (
        <p className="mt-2 text-3xl font-bold text-secondary-900">{value}</p>
      )}
    </div>
  );
}

export function DashboardPage() {
  const { profile } = useAuth();

  const { data: activeProjectCount } = useQuery({
    queryKey: ['dashboard', 'activeProjects'],
    queryFn: async () => {
      const { count, error } = await supabase
        .from('projects')
        .select('*', { count: 'exact', head: true })
        .eq('status', 'active')
        .is('deleted_at', null);
      if (error) throw error;
      return count ?? 0;
    },
  });

  const { data: activeVendorCount } = useQuery({
    queryKey: ['dashboard', 'activeVendors'],
    queryFn: async () => {
      const { count, error } = await supabase
        .from('vendors')
        .select('*', { count: 'exact', head: true })
        .eq('status', 'active')
        .is('deleted_at', null);
      if (error) throw error;
      return count ?? 0;
    },
  });

  const { openTaskCount, pendingBidCount, isLoading: countsLoading } = useDashboardCounts();

  const currentDate = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  const visibleCards = QUICK_NAV_CARDS.filter(
    (card) => !card.adminOnly || profile?.role === 'admin',
  );

  const roleLabel = profile?.role === 'admin' ? 'Administrator' : 'Project Manager';

  return (
    <div className="space-y-8">
      {/* Welcome header */}
      <div>
        <h1 className="text-2xl font-semibold text-secondary-900">
          Welcome back, {profile?.full_name?.split(' ')[0] || 'User'}
        </h1>
        <p className="mt-1 text-sm text-secondary-500">
          {currentDate} &middot; {roleLabel}
        </p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatPlaceholder label="Active Projects" value={activeProjectCount != null ? String(activeProjectCount) : '--'} />
        <StatPlaceholder
          label="Open Tasks"
          value={openTaskCount != null ? String(openTaskCount) : '0'}
          isLoading={countsLoading && openTaskCount == null}
        />
        <StatPlaceholder
          label="Pending Bids"
          value={pendingBidCount != null ? String(pendingBidCount) : '0'}
          isLoading={countsLoading && pendingBidCount == null}
        />
        <StatPlaceholder label="Active Vendors" value={activeVendorCount != null ? String(activeVendorCount) : '--'} />
      </div>

      {/* Quick navigation cards */}
      <div>
        <h2 className="text-lg font-semibold text-secondary-900">Quick Access</h2>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visibleCards.map((card) => (
            <Link
              key={card.title}
              to={card.href}
              className="group rounded-lg border border-secondary-200 bg-white p-6 shadow-sm transition-shadow hover:shadow-md"
            >
              <div className="flex items-center gap-3">
                <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-50 text-primary-600 transition-colors group-hover:bg-primary-100">
                  {card.icon}
                </span>
                <h3 className="text-base font-semibold text-secondary-900">{card.title}</h3>
              </div>
              <p className="mt-3 text-sm text-secondary-500">{card.description}</p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
