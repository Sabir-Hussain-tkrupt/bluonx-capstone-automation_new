import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchProjects } from '@/features/projects/api/project.queries';

/**
 * Fetch the project list via Supabase direct read (RLS protected).
 *
 * @example
 * const { data: projects, isLoading, error } = useProjects();
 */
export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects.list(),
    queryFn: fetchProjects,
  });
}
