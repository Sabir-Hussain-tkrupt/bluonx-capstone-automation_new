import axios from 'axios';
import type { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getAccessToken } from '@/services/auth.service';

// ─── API Error Type ───────────────────────────────────────────────────
/**
 * Standardized error for all API failures (both Supabase and FastAPI).
 * Components display `message`; `code` and `details` are for debugging.
 *
 * This is a real `Error` subclass, not a plain object, for three reasons:
 * it carries a stack trace, `instanceof` narrowing works without casting,
 * and React Query's `TError` defaults to `Error` — rejecting with a bare
 * object forced every consumer to cast its way back to this shape.
 * Mirrors `PortalApiError` on the vendor-portal side.
 */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: unknown;

  constructor(message: string, code: string, status: number, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

/** Narrow an `unknown` rejection to `ApiError` so `.status`/`.code` are readable. */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/**
 * Wrap a Supabase error (`{ message, code }`) as an `ApiError`. Direct
 * Supabase reads bypass the axios interceptor, so they need their own
 * conversion. `status` is 0 unless the caller can map one — most Supabase
 * failures have no HTTP status worth surfacing, but `PGRST116` (no rows
 * from `.single()`) is a genuine 404 and callers pass that in.
 */
export function fromSupabaseError(
  error: { message: string; code?: string },
  status = 0,
): ApiError {
  return new ApiError(error.message, error.code ?? 'SUPABASE_ERROR', status, error);
}

/**
 * Pull a user-facing message off a rejected API error, falling back to a fixed
 * string. Preferring the server message keeps 409 guard explanations and 403
 * permission text intact instead of replacing them with a generic fallback.
 *
 * Only real `Error`s are trusted for a message — that covers `ApiError` plus
 * Supabase auth errors. Anything else gets the fallback, so an internal
 * failure never leaks a raw runtime message into the UI.
 */
export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message || fallback : fallback;
}

// ─── Axios Instance ───────────────────────────────────────────────────
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export const api = axios.create({
  baseURL: `${apiBaseUrl}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30_000,
});

// ─── Request Interceptor: Inject JWT ──────────────────────────────────
api.interceptors.request.use(
  async (config: InternalAxiosRequestConfig) => {
    const token = await getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error),
);

// ─── Error Normalization ──────────────────────────────────────────────
/**
 * Translate a raw Axios failure into the `ApiError` the UI handles. Lives
 * outside the interceptor so the status/code/message mapping is unit-testable
 * without standing up an HTTP layer.
 */
export function normalizeAxiosError(
  error: AxiosError<{ detail?: string; message?: string }>,
): ApiError {
  if (error.response) {
    const { status, data } = error.response;

    // FastAPI returns errors as { detail: "..." }
    let message = data?.detail ?? data?.message ?? error.message;
    let code = 'UNKNOWN_ERROR';

    switch (status) {
      case 400:
        code = 'BAD_REQUEST';
        break;
      case 401:
        code = 'UNAUTHORIZED';
        message = 'Your session has expired. Please sign in again.';
        break;
      case 403:
        code = 'FORBIDDEN';
        message = 'You do not have permission to perform this action.';
        break;
      case 404:
        code = 'NOT_FOUND';
        message = 'The requested resource was not found.';
        break;
      case 409:
        code = 'CONFLICT';
        break;
      case 422:
        code = 'VALIDATION_ERROR';
        // Keep a server-supplied string detail (our services raise
        // HTTPException(422, detail="…") with a specific reason, e.g. a
        // past/invalid milestone date). FastAPI's own request-validation 422s
        // put an array of error objects in `detail` — fall back to generic for
        // those so the user never sees "[object Object]".
        message =
          typeof data?.detail === 'string' ? data.detail : 'Please check your input and try again.';
        break;
      case 500:
        code = 'SERVER_ERROR';
        message = 'A server error occurred. Please try again later.';
        break;
    }

    return new ApiError(message, code, status, data);
  }

  if (error.request) {
    return new ApiError(
      'Unable to reach the server. Check your connection.',
      'NETWORK_ERROR',
      0,
    );
  }

  return new ApiError('An unexpected error occurred', 'UNKNOWN_ERROR', 0);
}

// ─── Response Interceptor: Normalize Errors ───────────────────────────
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string; message?: string }>) =>
    Promise.reject(normalizeAxiosError(error)),
);
