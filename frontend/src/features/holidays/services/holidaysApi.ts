/**
 * Holiday calendar data layer — thin router.
 *
 * Dispatches every call to either the in-memory mock (`holidaysApi.mock.ts`)
 * or the real backend (`holidaysApi.real.ts`). Both satisfy `HolidaysApi`, so
 * the two cannot drift without a compile error.
 *
 * All consumers import the named functions from THIS file — the split is
 * invisible to them.
 *
 * Unlike the vendor portal (which keys its mock/real swap off `VITE_DEMO_MODE`),
 * this router is pinned to the mock via `USE_MOCK_HOLIDAYS`. The `holidays`
 * table and its endpoints do not exist yet, and both dev and prod default
 * `VITE_DEMO_MODE=false`, so keying off it would leave this page non-functional
 * in normal development. When the backend lands: implement `holidaysApi.real.ts`
 * and flip this one constant (or point it at an env flag).
 */
import { mockHolidaysApi } from './holidaysApi.mock';
import { realHolidaysApi } from './holidaysApi.real';
import type { HolidaysApi } from './holidaysApi.types';

const USE_MOCK_HOLIDAYS = true;
const impl: HolidaysApi = USE_MOCK_HOLIDAYS ? mockHolidaysApi : realHolidaysApi;

// Arrow wrappers (not bare re-exports) preserve `this` binding to the chosen
// impl object and keep the types sharp at each call site.
export const listHolidays: HolidaysApi['listHolidays'] = (year) => impl.listHolidays(year);
export const createHoliday: HolidaysApi['createHoliday'] = (input) => impl.createHoliday(input);
export const createHolidayRange: HolidaysApi['createHolidayRange'] = (input) =>
  impl.createHolidayRange(input);
export const updateHoliday: HolidaysApi['updateHoliday'] = (input) => impl.updateHoliday(input);
export const deleteHoliday: HolidaysApi['deleteHoliday'] = (id) => impl.deleteHoliday(id);

export type {
  Holiday,
  HolidaySource,
  CreateHolidayInput,
  CreateHolidayRangeInput,
  UpdateHolidayInput,
  HolidayErrorCode,
  HolidayValidationError,
  HolidaysApi,
} from './holidaysApi.types';
