/**
 * Test fixture for API failures.
 *
 * Production never rejects with a bare `{ message, status }` object — the axios
 * response interceptor and the Supabase converters both produce a real
 * `ApiError`, and consumers narrow with `instanceof`. Tests must build the same
 * thing or they assert against a shape that cannot occur.
 */
import { ApiError } from '@/lib/api';

/** Build an `ApiError` the way the interceptor would, with sensible defaults. */
export function makeApiError(
  message: string,
  status = 500,
  code = 'TEST_ERROR',
  details?: unknown,
): ApiError {
  return new ApiError(message, code, status, details);
}
