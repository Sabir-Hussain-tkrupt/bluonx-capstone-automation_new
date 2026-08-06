import { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { skipToken, useQueries } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { resolveTrail, type EntityKind, type ResolvedEntityLabel } from '@/lib/breadcrumbs';
import type { BreadcrumbItem } from '@/components/ui/Breadcrumbs';

/** Where each entity's display name lives in the query cache. */
const ENTITY_SOURCES: Record<
  EntityKind,
  { key: (id: string) => readonly unknown[]; name: (data: Record<string, unknown>) => string | undefined }
> = {
  project: {
    key: (id) => queryKeys.projects.detail(id),
    name: (d) => d.name as string | undefined,
  },
  task: {
    key: (id) => queryKeys.tasks.detail(id),
    name: (d) => d.name as string | undefined,
  },
  vendor: {
    key: (id) => queryKeys.vendors.detail(id),
    name: (d) => d.company_name as string | undefined,
  },
  milestone: {
    key: (id) => queryKeys.milestones.detail(id),
    name: (d) => d.name as string | undefined,
  },
  bidPackage: {
    key: (id) => queryKeys.bidPackages.detail(id),
    // The package's own h1 leads with the task name, which the parent crumb
    // already carries, so the round is the only new information here.
    name: (d) => (d.round_number == null ? undefined : `Round ${d.round_number}`),
  },
  bidTemplate: {
    key: (id) => queryKeys.bidTemplates.detail(id),
    name: (d) => d.name as string | undefined,
  },
};

/**
 * Breadcrumb items for the current route.
 *
 * Structure comes from the route config in lib/breadcrumbs (not from splitting
 * the pathname), and entity names are read from the React Query cache the page
 * itself populates. The reads use `skipToken`, so this hook subscribes to cache
 * entries but can never issue a request of its own: breadcrumbs add no network
 * traffic and no loading state. Until a page's fetch lands, the crumb shows its
 * fallback ("Project", "Task", ...) and swaps to the real name on arrival.
 */
export function useBreadcrumbs(): BreadcrumbItem[] {
  const { pathname } = useLocation();

  const trail = useMemo(() => resolveTrail(pathname), [pathname]);

  const entityCrumbs = useMemo(
    () => trail.filter((c): c is { label: ResolvedEntityLabel; href?: string } =>
      typeof c.label !== 'string'),
    [trail],
  );

  const cached = useQueries({
    queries: entityCrumbs.map((c) => ({
      queryKey: ENTITY_SOURCES[c.label.entity].key(c.label.id),
      queryFn: skipToken,
    })),
  });

  return useMemo(() => {
    let entityIndex = 0;

    return trail.map(({ label, href }) => {
      if (typeof label === 'string') return { label, href };

      const data = cached[entityIndex++]?.data as Record<string, unknown> | undefined;
      const name = data ? ENTITY_SOURCES[label.entity].name(data) : undefined;
      return { label: name || label.fallback, href };
    });
  }, [trail, cached]);
}
