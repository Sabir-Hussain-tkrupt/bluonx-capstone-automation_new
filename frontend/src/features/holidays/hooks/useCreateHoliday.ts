import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { createHoliday } from '../services/holidaysApi';
import type { CreateHolidayInput } from '../services/holidaysApi';

export function useCreateHoliday() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: CreateHolidayInput) => createHoliday(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.holidays.lists() });
    },
  });
}
