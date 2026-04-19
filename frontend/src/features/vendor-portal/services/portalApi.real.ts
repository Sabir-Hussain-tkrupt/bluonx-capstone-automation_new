/**
 * Real implementation of the vendor portal API.
 *
 * Phase 5 wiring ships incrementally:
 *   - Task 5.2 (this file): validateToken, request/response interceptors
 *   - Task 5.3: createDraft / updateDraft / submitBid / downloadProjectDocument
 *   - Task 5.5: uploadAttachment / deleteAttachment
 *
 * Methods not yet wired throw `Not implemented yet — Task 5.X` so that an
 * accidental call in dev surfaces immediately rather than returning
 * undefined and corrupting downstream state.
 *
 * JWT state lives here because the real Axios request interceptor is the
 * only consumer that actually needs it. The mock implementation keeps a
 * matching no-op so the `PortalApi` contract is satisfied on both sides.
 *
 * Selection of mock vs. real is done by `portalApi.ts` via the
 * `VITE_DEMO_MODE` flag. Never import from this file directly.
 */

import axios, { type AxiosError } from 'axios';
import type { ValidateTokenResponse } from '../types/portal';
import { PortalApiError, type PortalApiErrorCode } from '../types/portal';
import type { PortalApi } from './portalApi.types';

// ─── Axios instance ─────────────────────────────────────────────────
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const realAxios = axios.create({
  baseURL: `${apiBaseUrl}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
});

// ─── JWT state (shared by the request interceptor) ──────────────────
let currentVendorJwt: string | null = null;

function setVendorJwt(token: string | null): void {
  currentVendorJwt = token;
}

function getVendorJwt(): string | null {
  return currentVendorJwt;
}

realAxios.interceptors.request.use((config) => {
  if (currentVendorJwt) {
    config.headers.Authorization = `Bearer ${currentVendorJwt}`;
  }
  return config;
});

// ─── 401 handler registration ───────────────────────────────────────
// The response interceptor runs outside React, so it cannot call
// useNavigate or setState directly. VendorPortalContext registers a
// callback on mount that clears session state and routes the user
// to /bid/expired — without forcing a full page reload.
let onAuthFailure: (() => void) | null = null;

function setAuthFailureHandler(fn: (() => void) | null): void {
  onAuthFailure = fn;
}

realAxios.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && onAuthFailure) {
      onAuthFailure();
    }
    return Promise.reject(error);
  },
);

// ─── Error mapping ──────────────────────────────────────────────────
// Translates a raw Axios error into the `PortalApiError` the UI already
// handles (see MagicLinkLandingPage). Status → code mapping is the
// single source of truth for the validate-token flow.
function mapAxiosErrorToPortalError(err: unknown): PortalApiError {
  if (!axios.isAxiosError(err)) {
    return new PortalApiError('UNKNOWN', 'Unexpected error', 0);
  }
  if (!err.response) {
    return new PortalApiError('NETWORK', 'Network error — please try again.', 0);
  }
  const status = err.response.status;
  const detail =
    (err.response.data as { detail?: string } | undefined)?.detail ?? err.message;

  const code: PortalApiErrorCode = (() => {
    switch (status) {
      case 404:
        return 'TOKEN_INVALID';
      case 409:
        return 'ALREADY_SUBMITTED';
      case 410:
        return 'TOKEN_EXPIRED';
      case 423:
        return 'BIDDING_CLOSED';
      // Rate-limited. From the UX perspective the bid link simply can't
      // be validated right now — showing "invalid" is the safest default
      // and matches the existing PortalApiErrorCode union.
      case 429:
        return 'TOKEN_INVALID';
      default:
        return 'UNKNOWN';
    }
  })();

  return new PortalApiError(code, detail, status);
}

// ─── validateToken (POST /vendor-auth/validate-token) ───────────────
async function validateToken(token: string): Promise<ValidateTokenResponse> {
  try {
    const { data } = await realAxios.post<ValidateTokenResponse>(
      '/vendor-auth/validate-token',
      { token },
    );
    return data;
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

// ─── Throwing stubs — filled in by Tasks 5.3–5.5 ────────────────────
function notImplemented(task: string): never {
  throw new Error(`Not implemented yet — ${task}`);
}

export const realPortalApi: PortalApi = {
  setVendorJwt,
  getVendorJwt,
  setAuthFailureHandler,
  validateToken,
  createDraft: async () => notImplemented('Task 5.3'),
  updateDraft: async () => notImplemented('Task 5.3'),
  submitBid: async () => notImplemented('Task 5.4'),
  uploadAttachment: async () => notImplemented('Task 5.5'),
  deleteAttachment: async () => notImplemented('Task 5.5'),
  downloadProjectDocument: async () => notImplemented('Task 5.3'),
};
