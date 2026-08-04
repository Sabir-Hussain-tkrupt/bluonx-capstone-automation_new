import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Folder, Settings, Users } from 'lucide-react';
import { useAuth } from '@/contexts/AuthContext';
import { ROUTES } from '@/constants/routes';
import { supabase } from '@/lib/supabase';
import { useDashboardCounts } from '@/features/dashboard/hooks/useDashboardCounts';
import { AttentionMilestonesCard } from '@/features/dashboard/components/AttentionMilestonesCard';
import { StatCard } from '@/components/ui/StatCard';
import { Card } from '@/components/ui/Card';

function VendorsIcon() {
  return <Users className="h-5 w-5" aria-hidden="true" />;
}

function ProjectsIcon() {
  return <Folder className="h-5 w-5" aria-hidden="true" />;
}

function SettingsIcon() {
  return <Settings className="h-5 w-5" aria-hidden="true" />;
}

interface QuickNavCard {
  title: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  /** Icon color only — background stays neutral so cards don't compete with the stat/attention sections above. */
  iconColor: string;
  adminOnly?: boolean;
}

const QUICK_NAV_CARDS: QuickNavCard[] = [
  {
    title: 'Vendors',
    description: 'Manage vendor profiles, contacts, and trade certifications.',
    href: ROUTES.VENDORS,
    icon: <VendorsIcon />,
    iconColor: 'text-primary-600',
  },
  {
    title: 'Projects',
    description: 'View and manage development and construction projects.',
    href: ROUTES.PROJECTS,
    icon: <ProjectsIcon />,
    iconColor: 'text-accent-600',
  },
  {
    title: 'Settings',
    description: 'Manage users, trades, and system configuration.',
    href: ROUTES.SETTINGS,
    icon: <SettingsIcon />,
    iconColor: 'text-secondary-600',
    adminOnly: true,
  },
];

function StatSkeleton() {
  return (
    <span className="block h-9 w-16 animate-pulse rounded bg-secondary-200" aria-hidden="true" />
  );
}

export function DashboardPage() {
  const { profile } = useAuth();

  const { data: activeProjectCount, isLoading: activeProjectsLoading } = useQuery({
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

  const { data: activeVendorCount, isLoading: activeVendorsLoading } = useQuery({
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
        <StatCard
          label="Active Projects"
          accent="primary"
          value={
            activeProjectsLoading && activeProjectCount == null
              ? <StatSkeleton />
              : String(activeProjectCount ?? 0)
          }
        />
        <StatCard
          label="Open Tasks"
          accent="primary"
          value={
            countsLoading && openTaskCount == null
              ? <StatSkeleton />
              : String(openTaskCount ?? 0)
          }
        />
        <StatCard
          label="Pending Bids"
          accent="primary"
          value={
            countsLoading && pendingBidCount == null
              ? <StatSkeleton />
              : String(pendingBidCount ?? 0)
          }
        />
        <StatCard
          label="Active Vendors"
          accent="primary"
          value={
            activeVendorsLoading && activeVendorCount == null
              ? <StatSkeleton />
              : String(activeVendorCount ?? 0)
          }
        />
      </div>

      {/* Milestones needing PM attention (paused check-in cycle) */}
      <AttentionMilestonesCard />

      {/* Quick navigation cards */}
      <div>
        <h2 className="text-lg font-semibold text-secondary-900">Quick Access</h2>
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {visibleCards.map((card) => (
            <Link key={card.title} to={card.href} className="group block">
              <Card padding="sm" className="transition-shadow group-hover:shadow-md">
                <div className="flex items-center gap-3">
                  <span
                    className={`flex h-9 w-9 items-center justify-center rounded-lg bg-secondary-100 transition-colors group-hover:bg-secondary-200 ${card.iconColor}`}
                  >
                    {card.icon}
                  </span>
                  <h3 className="text-base font-semibold text-secondary-900">{card.title}</h3>
                </div>
                <p className="mt-3 text-sm text-secondary-500">{card.description}</p>
              </Card>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
