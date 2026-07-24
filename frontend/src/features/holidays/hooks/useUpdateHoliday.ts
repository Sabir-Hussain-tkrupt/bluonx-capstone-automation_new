import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { updateHoliday } from '../services/holidaysApi';
import type { UpdateHolidayInput } from '../services/holidaysApi';

export function useUpdateHoliday() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UpdateHolidayInput) => updateHoliday(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.holidays.lists() });
    },
  });
}
