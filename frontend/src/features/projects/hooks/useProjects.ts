import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchProjects } from '@/features/projects/api/project.queries';
import type { ProjectListFilters } from '@/features/projects/api/project.queries';

/**
 * Fetch the project list with optional filters via Supabase direct read (RLS protected).
 */
export function useProjects(filters?: ProjectListFilters) {
  return useQuery({
    queryKey: queryKeys.projects.list(filters as Record<string, unknown>),
    queryFn: () => fetchProjects(filters),
  });
}
