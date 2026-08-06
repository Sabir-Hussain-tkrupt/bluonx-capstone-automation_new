/**
 * Holiday calendar data layer.
 *
 * Never import from this file directly — import from `holidaysApi.ts`.
 *
 * Follows the app's read/write split:
 *   - listHolidays  → Supabase directly, protected by the
 *     `holidays_select_authenticated` RLS policy (any active user may read).
 *   - create/update/delete → FastAPI, which enforces admin in application code.
 *     Those handlers hold the service_role key and bypass RLS, so that check is
 *     the real gate.
 *
 * The DB column is `holiday_date`; the UI type calls it `date`. The mapping
 * lives here, at the seam, so no component or hook has to know.
 *
 * Validation messages are NOT reproduced here. The past-date freeze and the two
 * caps come from the DB guardrail trigger as PT422, the weekend rule from the
 * API, and duplicates as a 409 — all of them worded server-side and passed
 * through by the axios interceptor, which preserves `detail` verbatim on 409 and
 * on a 422 whose detail is a string.
 */
import { supabase } from '@/lib/supabase';
import { api, fromSupabaseError } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';
import type { Holiday, HolidaysApi } from './holidaysApi.types';

/** The `holidays` row shape as it comes back from Supabase. */
interface HolidayRow {
  id: string;
  holiday_date: string;
  name: string;
  source: Holiday['source'];
  created_at: string;
  updated_at: string;
}

function toHoliday(row: HolidayRow): Holiday {
  return {
    id: row.id,
    date: row.holiday_date,
    name: row.name,
    source: row.source,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

export const realHolidaysApi: HolidaysApi = {
  async listHolidays(year) {
    const { data, error } = await supabase
      .from('holidays')
      .select('id, holiday_date, name, source, created_at, updated_at')
      .gte('holiday_date', `${year}-01-01`)
      .lte('holiday_date', `${year}-12-31`)
      .order('holiday_date', { ascending: true });

    if (error) throw fromSupabaseError(error);

    return ((data ?? []) as unknown as HolidayRow[]).map(toHoliday);
  },

  async createHoliday(input) {
    const { data } = await api.post(API_ENDPOINTS.HOLIDAYS, {
      holiday_date: input.date,
      name: input.name,
    });
    return toHoliday(data as HolidayRow);
  },

  async createHolidayRange(input) {
    const { data } = await api.post(API_ENDPOINTS.HOLIDAYS_RANGE, {
      start_date: input.startDate,
      end_date: input.endDate,
      name: input.name,
    });
    return (data as HolidayRow[]).map(toHoliday);
  },

  async updateHoliday(input) {
    const { data } = await api.patch(API_ENDPOINTS.HOLIDAY(input.id), {
      holiday_date: input.date,
      name: input.name,
    });
    return toHoliday(data as HolidayRow);
  },

  async deleteHoliday(id) {
    await api.delete(API_ENDPOINTS.HOLIDAY(id));
  },
};
