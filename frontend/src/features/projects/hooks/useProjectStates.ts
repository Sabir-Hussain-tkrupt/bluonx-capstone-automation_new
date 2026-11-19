import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchProjectStates } from '@/features/projects/api/project.queries';

/** States used by projects (active, or archived), for the list's "State" filter. */
export function useProjectStates(archived = false) {
  return useQuery({
    queryKey: queryKeys.projects.states(archived),
    queryFn: () => fetchProjectStates(archived),
    staleTime: 60_000,
  });
}
