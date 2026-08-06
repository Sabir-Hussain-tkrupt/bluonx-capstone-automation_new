/**
 * Holiday calendar data layer — public surface.
 *
 * All consumers import the named functions from THIS file, so the split between
 * the Supabase read path and the FastAPI write path stays invisible to hooks and
 * components. The implementation lives in `holidaysApi.real.ts`, typed as
 * `HolidaysApi` so it cannot drift from the contract without a compile error.
 */
import { realHolidaysApi } from './holidaysApi.real';
import type { HolidaysApi } from './holidaysApi.types';

// Arrow wrappers (not bare re-exports) preserve `this` binding to the impl
// object and keep the types sharp at each call site.
export const listHolidays: HolidaysApi['listHolidays'] = (year) =>
  realHolidaysApi.listHolidays(year);
export const createHoliday: HolidaysApi['createHoliday'] = (input) =>
  realHolidaysApi.createHoliday(input);
export const createHolidayRange: HolidaysApi['createHolidayRange'] = (input) =>
  realHolidaysApi.createHolidayRange(input);
export const updateHoliday: HolidaysApi['updateHoliday'] = (input) =>
  realHolidaysApi.updateHoliday(input);
export const deleteHoliday: HolidaysApi['deleteHoliday'] = (id) =>
  realHolidaysApi.deleteHoliday(id);

export type {
  Holiday,
  HolidaySource,
  CreateHolidayInput,
  CreateHolidayRangeInput,
  UpdateHolidayInput,
  HolidaysApi,
} from './holidaysApi.types';
