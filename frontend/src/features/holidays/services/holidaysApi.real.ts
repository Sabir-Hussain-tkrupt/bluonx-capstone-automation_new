/**
 * Real-backend implementation of the holiday calendar — NOT WIRED YET.
 *
 * Never import from this file directly — import from `holidaysApi.ts`.
 *
 * The `holidays` table and its FastAPI endpoints land in a later phase. Until
 * then every method throws a clear error, and the router (`holidaysApi.ts`)
 * points at the mock. When the backend exists, fill in the four methods below
 * and flip `USE_MOCK_HOLIDAYS` in the router — no component, hook, or type
 * change is required, because both impls satisfy the same `HolidaysApi`.
 *
 * Intended shape, following the app's read/write split:
 *   - listHolidays → direct Supabase read (RLS-protected), e.g.
 *       supabase.from('holidays').select('*')
 *         .gte('date', `${year}-01-01`).lte('date', `${year}-12-31`)
 *         .order('date', { ascending: true })
 *     mapped to `Holiday[]`, rejecting with the shared `ApiError` shape.
 *   - create/update/delete → FastAPI writes via `api` + `API_ENDPOINTS.HOLIDAYS`.
 *     The server enforces the same rules and returns `HolidayValidationError`.
 */
import type { ApiError } from '@/lib/api';
import type { HolidaysApi } from './holidaysApi.types';

function notWired(): never {
  const error: ApiError = {
    message: 'The holiday calendar backend is not wired up yet.',
    code: 'NOT_IMPLEMENTED',
    status: 501,
  };
  throw error;
}

export const realHolidaysApi: HolidaysApi = {
  async listHolidays() {
    return notWired();
  },
  async createHoliday() {
    return notWired();
  },
  async createHolidayRange() {
    return notWired();
  },
  async updateHoliday() {
    return notWired();
  },
  async deleteHoliday() {
    return notWired();
  },
};
