import axios from 'axios';
import type { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getAccessToken } from '@/services/auth.service';

// ─── API Error Type ───────────────────────────────────────────────────
/**
 * Standardized error shape for all API errors (both Supabase and FastAPI).
 * Components display `message`; `code` and `details` are for debugging.
 */
export interface ApiError {
  message: string;
  code: string;
  status: number;
  details?: unknown;
}

/**
 * Pull a user-facing message off a rejected API error, falling back to a fixed
 * string. Preferring the server message keeps 409 guard explanations and 403
 * permission text intact instead of replacing them with a generic fallback.
 */
export function errorMessage(error: unknown, fallback: string): string {
  return (error as ApiError | undefined)?.message || fallback;
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

// ─── Response Interceptor: Normalize Errors ───────────────────────────
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: string; message?: string }>) => {
    const apiError: ApiError = {
      message: 'An unexpected error occurred',
      code: 'UNKNOWN_ERROR',
      status: error.response?.status ?? 0,
    };

    if (error.response) {
      const { status, data } = error.response;
      apiError.status = status;
      apiError.details = data;

      // FastAPI returns errors as { detail: "..." }
      apiError.message = data?.detail ?? data?.message ?? error.message;

      switch (status) {
        case 400:
          apiError.code = 'BAD_REQUEST';
          break;
        case 401:
          apiError.code = 'UNAUTHORIZED';
          apiError.message = 'Your session has expired. Please sign in again.';
          break;
        case 403:
          apiError.code = 'FORBIDDEN';
          apiError.message = 'You do not have permission to perform this action.';
          break;
        case 404:
          apiError.code = 'NOT_FOUND';
          apiError.message = 'The requested resource was not found.';
          break;
        case 409:
          apiError.code = 'CONFLICT';
          break;
        case 422:
          apiError.code = 'VALIDATION_ERROR';
          apiError.message = 'Please check your input and try again.';
          break;
        case 500:
          apiError.code = 'SERVER_ERROR';
          apiError.message = 'A server error occurred. Please try again later.';
          break;
      }
    } else if (error.request) {
      apiError.code = 'NETWORK_ERROR';
      apiError.message = 'Unable to reach the server. Check your connection.';
    }

    return Promise.reject(apiError);
  },
);
