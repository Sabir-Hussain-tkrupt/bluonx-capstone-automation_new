/**
 * Real implementation of the vendor portal API.
 *
 * Each method throws `Not implemented yet — Task 5.X` until the
 * matching backend endpoint lands. Failing loudly (vs. returning
 * undefined) makes accidental calls in dev impossible to miss.
 *
 * JWT state lives here because the real Axios interceptor is the
 * only consumer that actually needs it. The mock implementation
 * keeps a matching no-op so the `PortalApi` contract is satisfied
 * on both sides.
 *
 * Selection of mock vs. real is done by `portalApi.ts` via the
 * `VITE_DEMO_MODE` flag. Never import from this file directly.
 */

import axios from 'axios';
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

// Referenced so Task 5.2+ can swap throw-stubs for `realAxios.post(...)`
// calls. The `void` keeps the symbol alive without emitting dead code
// warnings while stubs are in place.
void realAxios;

// ─── Throwing stubs — filled in by Tasks 5.2–5.5 ────────────────────
function notImplemented(task: string): never {
  throw new Error(`Not implemented yet — ${task}`);
}

// Stubs take zero args — TypeScript allows a narrower signature to
// satisfy the wider `PortalApi` function types. Params will be
// reintroduced by Tasks 5.2–5.5 when real Axios calls are wired in.
// The `async` wrapper converts the throw into a rejected promise,
// so callers using `.catch()` (without `await`) behave correctly.
export const realPortalApi: PortalApi = {
  setVendorJwt,
  getVendorJwt,
  validateToken: async () => notImplemented('Task 5.2'),
  createDraft: async () => notImplemented('Task 5.3'),
  updateDraft: async () => notImplemented('Task 5.3'),
  submitBid: async () => notImplemented('Task 5.4'),
  uploadAttachment: async () => notImplemented('Task 5.3'),
  deleteAttachment: async () => notImplemented('Task 5.3'),
  downloadProjectDocument: async () => notImplemented('Task 5.3'),
};
