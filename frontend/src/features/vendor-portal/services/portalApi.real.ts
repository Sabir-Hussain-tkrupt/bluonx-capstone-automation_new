/**
 * Real implementation of the vendor portal API.
 *
 * Wired incrementally:
 *   - Task 5.2: validateToken + request/response interceptors
 *   - Task 5.3–5.6 (this file): draft CRUD, submit, attachments, downloads
 *
 * JWT state lives here because the real Axios request interceptor is the
 * only consumer that actually needs it. The mock implementation keeps a
 * matching no-op so the `PortalApi` contract is satisfied on both sides.
 *
 * Selection of mock vs. real is done by `portalApi.ts` via the
 * `VITE_DEMO_MODE` flag. Never import from this file directly.
 */

import axios, { type AxiosError } from 'axios';
import type {
  BidDraft,
  FormAttachment,
  MilestoneRespondResult,
  MilestoneValidateResponse,
  PortalFieldError,
  RevisionPrefillResponse,
  SubmissionAttachmentMeta,
  SubmitBidResult,
  ValidateTokenResponse,
} from '../types/portal';
import { PortalApiError, type PortalApiErrorCode } from '../types/portal';
import type {
  BidRevisionRequestResponse,
  DraftPayload,
  PortalApi,
} from './portalApi.types';

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
// Translates a raw Axios error into the `PortalApiError` the UI handles.
// Status → code mapping is the single source of truth across the whole
// portal API surface.
interface ErrorBody {
  detail?: string | { detail?: string; errors?: PortalFieldError[]; existing_submission_id?: string };
  errors?: PortalFieldError[];
  existing_submission_id?: string;
}

function extractDetailString(body: ErrorBody | undefined, fallback: string): string {
  if (!body) return fallback;
  if (typeof body.detail === 'string') return body.detail;
  if (body.detail && typeof body.detail === 'object' && typeof body.detail.detail === 'string') {
    return body.detail.detail;
  }
  return fallback;
}

function extractFieldErrors(body: ErrorBody | undefined): PortalFieldError[] | undefined {
  if (!body) return undefined;
  if (Array.isArray(body.errors)) return body.errors;
  if (body.detail && typeof body.detail === 'object' && Array.isArray(body.detail.errors)) {
    return body.detail.errors;
  }
  return undefined;
}

function extractExistingSubmissionId(body: ErrorBody | undefined): string | undefined {
  if (!body) return undefined;
  if (typeof body.existing_submission_id === 'string') return body.existing_submission_id;
  if (body.detail && typeof body.detail === 'object' && typeof body.detail.existing_submission_id === 'string') {
    return body.detail.existing_submission_id;
  }
  return undefined;
}

function mapAxiosErrorToPortalError(err: unknown): PortalApiError {
  if (!axios.isAxiosError(err)) {
    return new PortalApiError('UNKNOWN', 'Unexpected error', 0);
  }
  if (!err.response) {
    return new PortalApiError('NETWORK', 'Network error — please try again.', 0);
  }
  const status = err.response.status;
  const body = err.response.data as ErrorBody | undefined;
  const detailMsg = extractDetailString(body, err.message);
  const fieldErrors = extractFieldErrors(body);
  const existingId = extractExistingSubmissionId(body);

  const code: PortalApiErrorCode = (() => {
    switch (status) {
      case 404:
        return 'TOKEN_INVALID';
      case 409:
        // Distinguish concurrent-POST race (has existing_submission_id +
        // draft/submit distinction in detail) from the auth-time
        // already-submitted case (no id body, used by /validate-token).
        if (existingId) return 'DRAFT_CONFLICT';
        return 'ALREADY_SUBMITTED';
      case 410:
        return 'TOKEN_EXPIRED';
      case 422:
        if (fieldErrors && fieldErrors.length > 0) return 'VALIDATION_FAILED';
        return 'UNKNOWN';
      case 423: {
        // Package-closed vs. deadline-passed share status but differ in
        // detail. Keep the copy surfaces separate so the modal vs.
        // landing-page flows pick the right one.
        const detail = detailMsg.toLowerCase();
        if (detail.includes('deadline')) return 'DEADLINE_PASSED';
        return 'BIDDING_CLOSED';
      }
      case 429:
        // Rate-limited token validation path — same UX as invalid link.
        return 'TOKEN_INVALID';
      default:
        return 'UNKNOWN';
    }
  })();

  return new PortalApiError(code, detailMsg, status, {
    validationErrors: fieldErrors,
    existingSubmissionId: existingId,
  });
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

// ─── Draft CRUD (Tasks 5.3 / 5.6) ───────────────────────────────────
async function createDraft(payload: DraftPayload): Promise<BidDraft> {
  try {
    const { data } = await realAxios.post<BidDraft>('/vendor-portal/submissions', payload);
    return data;
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

async function updateDraft(id: string, payload: DraftPayload): Promise<BidDraft> {
  try {
    const { data } = await realAxios.put<BidDraft>(
      `/vendor-portal/submissions/${id}`,
      payload,
    );
    return data;
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

// ─── Submit (Task 5.4) ──────────────────────────────────────────────
async function submitBid(submissionId: string): Promise<SubmitBidResult> {
  try {
    const { data } = await realAxios.post<SubmitBidResult>(
      `/vendor-portal/submissions/${submissionId}/submit`,
    );
    return data;
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

// ─── Attachments (Task 5.5) ─────────────────────────────────────────
interface BackendAttachmentResponse {
  id: string;
  file_name: string;
  file_size: number;
  file_type: string | null;
  uploaded_at: string;
}

async function uploadAttachment(
  submissionId: string,
  file: File,
): Promise<FormAttachment> {
  const fd = new FormData();
  fd.append('file', file);
  try {
    const { data } = await realAxios.post<BackendAttachmentResponse>(
      `/vendor-portal/submissions/${submissionId}/attachments`,
      fd,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    // The UI's FormAttachment keeps the File object for icon rendering.
    // Preserve the one the user dropped so the listing looks identical
    // to the Task 5.1 behaviour.
    return {
      id: data.id,
      file,
      name: data.file_name,
      size: data.file_size,
      uploadedAt: data.uploaded_at,
    };
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

async function deleteAttachment(
  submissionId: string,
  attachmentId: string,
): Promise<void> {
  try {
    await realAxios.delete(
      `/vendor-portal/submissions/${submissionId}/attachments/${attachmentId}`,
    );
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

// ─── Revision prefill + attachment metadata (Phase E) ───────────────
async function getRevisionPrefill(
  originalSubmissionId: string,
): Promise<RevisionPrefillResponse> {
  try {
    const { data } = await realAxios.get<RevisionPrefillResponse>(
      `/vendor-portal/submissions/${originalSubmissionId}/revision-prefill`,
    );
    return data;
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

async function listSubmissionAttachments(
  submissionId: string,
): Promise<SubmissionAttachmentMeta[]> {
  try {
    const { data } = await realAxios.get<SubmissionAttachmentMeta[]>(
      `/vendor-portal/submissions/${submissionId}/attachments`,
    );
    return data;
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

async function declineRevisionRequest(
  revisionRequestId: string,
  decline_reason?: string,
): Promise<BidRevisionRequestResponse> {
  // Omit the field entirely when blank so the backend stores SQL NULL
  // (matches its Optional[str] semantics — never send "").
  const trimmed = decline_reason?.trim();
  const body = trimmed ? { decline_reason: trimmed } : {};
  try {
    const { data } = await realAxios.post<BidRevisionRequestResponse>(
      `/vendor-portal/revision-requests/${revisionRequestId}/decline`,
      body,
    );
    return data;
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

// ─── Milestone check-in (Phase 10.2) ────────────────────────────────
async function validateMilestoneToken(
  token: string,
): Promise<MilestoneValidateResponse> {
  try {
    const { data } = await realAxios.post<MilestoneValidateResponse>(
      '/vendor-auth/validate-milestone-token',
      { token },
    );
    return data;
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

async function respondToMilestone(
  milestoneAlertId: string,
  value: 'yes' | 'no',
): Promise<MilestoneRespondResult> {
  try {
    const { data } = await realAxios.post<MilestoneRespondResult>(
      `/vendor-portal/milestones/${milestoneAlertId}/respond`,
      { value },
    );
    return data;
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

// ─── Project document download (Task 5.3) ───────────────────────────
async function downloadProjectDocument(documentId: string): Promise<string> {
  try {
    const { data } = await realAxios.get<{ url: string; expires_in: number }>(
      `/vendor-portal/documents/${documentId}/download`,
    );
    return data.url;
  } catch (err) {
    throw mapAxiosErrorToPortalError(err);
  }
}

export const realPortalApi: PortalApi = {
  setVendorJwt,
  getVendorJwt,
  setAuthFailureHandler,
  validateToken,
  createDraft,
  updateDraft,
  submitBid,
  uploadAttachment,
  deleteAttachment,
  downloadProjectDocument,
  getRevisionPrefill,
  listSubmissionAttachments,
  declineRevisionRequest,
  validateMilestoneToken,
  respondToMilestone,
};
