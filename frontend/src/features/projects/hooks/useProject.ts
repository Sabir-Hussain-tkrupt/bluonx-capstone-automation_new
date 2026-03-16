import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchProjectById } from '@/features/projects/api/project.queries';

/**
 * Fetch a single project by ID via Supabase direct read (RLS protected).
 */
export function useProject(id: string) {
  return useQuery({
    queryKey: queryKeys.projects.detail(id),
    queryFn: () => fetchProjectById(id),
    enabled: !!id,
  });
}
