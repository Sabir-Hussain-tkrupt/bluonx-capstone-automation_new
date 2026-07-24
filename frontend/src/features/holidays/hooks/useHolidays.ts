import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import type { ApiError } from '@/lib/api';
import { listHolidays } from '../services/holidaysApi';
import type { Holiday } from '../services/holidaysApi';

/** Holidays for a calendar year, ascending by date. */
export function useHolidays(year: number) {
  return useQuery<Holiday[], ApiError>({
    queryKey: queryKeys.holidays.list(year),
    queryFn: () => listHolidays(year),
  });
}
