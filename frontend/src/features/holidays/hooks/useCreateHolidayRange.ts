import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createHolidayRange } from '../services/holidaysApi';
import type { CreateHolidayRangeInput } from '../services/holidaysApi';

export function useCreateHolidayRange() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateHolidayRangeInput) => createHolidayRange(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.holidays.lists() });
    },
  });
}
