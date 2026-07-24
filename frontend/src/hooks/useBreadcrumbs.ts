import { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';
import type { BreadcrumbItem } from '@/components/ui/Breadcrumbs';

/** Maps known URL segments to human-readable labels. */
const SEGMENT_LABELS: Record<string, string> = {
  dashboard: 'Dashboard',
  vendors: 'Vendors',
  projects: 'Projects',
  tasks: 'Tasks',
  bids: 'Bid Management',
  award: 'Award',
  settings: 'Settings',
  calendar: 'Holiday Calendar',
};

/** Detects dynamic route segments (UUIDs or numeric IDs). */
function isDynamicSegment(segment: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(segment)
    || /^\d+$/.test(segment);
}

/**
 * Generates breadcrumb items from the current URL path.
 *
 * Dynamic segments (UUIDs, numeric IDs) show "Details" as a placeholder.
 * Real entity names (vendor name, project name) will be resolved in Phase 3
 * when data-fetching hooks are available.
 */
export function useBreadcrumbs(): BreadcrumbItem[] {
  const { pathname } = useLocation();

  return useMemo(() => {
    const segments = pathname.split('/').filter(Boolean);

    // Dashboard page — single item, no link
    if (segments.length <= 1 && segments[0] === 'dashboard') {
      return [{ label: 'Dashboard' }];
    }

    const items: BreadcrumbItem[] = [
      { label: 'Dashboard', href: ROUTES.DASHBOARD },
    ];

    let accumulatedPath = '';

    for (let i = 0; i < segments.length; i++) {
      const segment = segments[i];
      accumulatedPath += `/${segment}`;
      const isLast = i === segments.length - 1;

      // Skip 'dashboard' — already added as root
      if (segment === 'dashboard') continue;

      if (isDynamicSegment(segment)) {
        items.push({
          label: 'Details',
          href: isLast ? undefined : accumulatedPath,
        });
      } else {
        items.push({
          label: SEGMENT_LABELS[segment] || segment,
          href: isLast ? undefined : accumulatedPath,
        });
      }
    }

    return items;
  }, [pathname]);
}
