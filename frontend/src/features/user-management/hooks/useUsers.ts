import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { fetchUsers } from '../api/user.queries';

export function useUsers() {
  return useQuery({
    queryKey: queryKeys.users.lists(),
    queryFn: fetchUsers,
    staleTime: 30_000,
  });
}
