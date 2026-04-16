/**
 * Mock Axios instance for the vendor portal.
 *
 * Why mock here (Task 5.1): backend endpoints (5.2–5.5) do not exist yet.
 * The shape of every response below matches the real contract exactly, so
 * Tasks 5.2–5.5 can replace the bodies of these functions with real HTTP
 * calls without touching any caller.
 */

import axios from 'axios';
import type {
  BidDraft,
  BidDraftLineItem,
  FormAttachment,
  SubmitBidResult,
  ValidateTokenResponse,
  VendorBidContext,
} from '../types/portal';
import { PortalApiError } from '../types/portal';

// ─── Axios instance (configured, but mocks bypass the network) ──────
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

export const portalApi = axios.create({
  baseURL: `${apiBaseUrl}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
});

/**
 * Mutable JWT holder so the request interceptor can always read the
 * latest token. Set by VendorPortalContext when a new token is issued.
 */
let currentVendorJwt: string | null = null;
export function setVendorJwt(token: string | null) {
  currentVendorJwt = token;
}
export function getVendorJwt(): string | null {
  return currentVendorJwt;
}

portalApi.interceptors.request.use((config) => {
  if (currentVendorJwt) {
    config.headers.Authorization = `Bearer ${currentVendorJwt}`;
  }
  return config;
});

// ─── Seed data (realistic construction project) ─────────────────────
const SEED_CONTEXT: VendorBidContext = {
  vendor: {
    id: 'vendor-summit-001',
    company_name: 'Summit Earthworks LLC',
    primary_contact_name: 'Marcus Delgado',
    email: 'marcus@summitearthworks.com',
    phone: '(602) 555-0147',
  },
  project: {
    id: 'proj-phoenix-001',
    name: 'Phoenix Logistics Park — Building C',
    location: 'Phoenix, AZ',
    address: '7420 W Buckeye Rd, Phoenix, AZ 85043',
  },
  task: {
    id: 'task-grading-001',
    name: 'Site Grading & Earthwork',
    description:
      'Mass excavation, cut/fill balancing, and final grading for Building C pad per approved civil drawings C-101 through C-110. Estimated quantities ±10%.',
    trade_name: 'Earthwork / Grading',
  },
  bid_package: {
    id: 'bp-grading-round-1',
    round_number: 1,
    // 7 days from now — gives a realistic countdown
    deadline: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
    instructions:
      'Please include mobilization as a separate line item. Unit prices should be all-inclusive (labor, equipment, fuel, overhead). Bid must be held firm for 30 days.',
  },
  bid_template: {
    id: 'tpl-grading-001',
    name: 'Site Grading — Structured',
    is_lump_sum: false,
    items: [
      {
        id: 'ti-001',
        description: 'Mobilization & Demobilization',
        item_type: 'lump_sum',
        unit_of_measure: null,
        sort_order: 1,
      },
      {
        id: 'ti-002',
        description: 'Clearing & Grubbing',
        item_type: 'unit_price',
        unit_of_measure: 'AC',
        sort_order: 2,
      },
      {
        id: 'ti-003',
        description: 'Cut and Fill (balanced on-site)',
        item_type: 'unit_price',
        unit_of_measure: 'CY',
        sort_order: 3,
      },
      {
        id: 'ti-004',
        description: 'Erosion Control (silt fence + inlet protection)',
        item_type: 'unit_price',
        unit_of_measure: 'LF',
        sort_order: 4,
      },
      {
        id: 'ti-005',
        description: 'Fine Grading to ±0.10 ft',
        item_type: 'unit_price',
        unit_of_measure: 'SF',
        sort_order: 5,
      },
    ],
  },
  project_documents: [
    {
      id: 'pd-001',
      file_name: 'Civil_Drawings_C-101_thru_C-110.pdf',
      file_size_bytes: 4_820_331,
      uploaded_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: 'pd-002',
      file_name: 'Geotech_Report_Phoenix_LogPark.pdf',
      file_size_bytes: 2_145_908,
      uploaded_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: 'pd-003',
      file_name: 'ALTA_Survey_Building_C.pdf',
      file_size_bytes: 1_328_554,
      uploaded_at: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
    },
  ],
  existing_draft: null,
};

// Cloner so callers can't mutate seed data accidentally.
function cloneContext(ctx: VendorBidContext): VendorBidContext {
  return JSON.parse(JSON.stringify(ctx)) as VendorBidContext;
}

// Artificial latency for realism in UI dev.
function delay(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

function uid(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

// ─── validateToken (mirrors POST /v1/vendor-auth/validate-token) ────
/**
 * Special tokens drive the error pages so the flows can be walked
 * end-to-end without a backend:
 *   - `expired-token`    → 410 TOKEN_EXPIRED
 *   - `invalid-token`    → 404 TOKEN_INVALID
 *   - `closed-token`     → 423 BIDDING_CLOSED
 *   - `submitted-token`  → 409 ALREADY_SUBMITTED
 * Any other token resolves to the happy-path context.
 */
export async function validateToken(token: string): Promise<ValidateTokenResponse> {
  await delay(1000);

  switch (token) {
    case 'expired-token':
      throw new PortalApiError('TOKEN_EXPIRED', 'This bid link has expired.', 410);
    case 'invalid-token':
      throw new PortalApiError('TOKEN_INVALID', 'This bid link is not recognized.', 404);
    case 'closed-token':
      throw new PortalApiError('BIDDING_CLOSED', 'Bidding for this package is closed.', 423);
    case 'submitted-token':
      throw new PortalApiError(
        'ALREADY_SUBMITTED',
        'A bid has already been submitted for this invitation.',
        409,
      );
    default:
      return {
        jwt: `mock.vendor.jwt.${uid('tok')}`,
        bid_context: cloneContext(SEED_CONTEXT),
      };
  }
}

// ─── Draft persistence ──────────────────────────────────────────────
export interface DraftPayload {
  vendor_notes: string;
  total_amount: number | null;
  line_items: BidDraftLineItem[];
  attachment_ids: string[];
}

export async function createDraft(payload: DraftPayload): Promise<BidDraft> {
  await delay(250);
  const draft: BidDraft = {
    id: uid('draft'),
    vendor_notes: payload.vendor_notes,
    total_amount: payload.total_amount,
    line_items: payload.line_items,
    attachment_ids: payload.attachment_ids,
    last_saved_at: new Date().toISOString(),
  };
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] createDraft →', draft);
  return draft;
}

export async function updateDraft(id: string, payload: DraftPayload): Promise<BidDraft> {
  await delay(250);
  const draft: BidDraft = {
    id,
    vendor_notes: payload.vendor_notes,
    total_amount: payload.total_amount,
    line_items: payload.line_items,
    attachment_ids: payload.attachment_ids,
    last_saved_at: new Date().toISOString(),
  };
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] updateDraft →', id, draft);
  return draft;
}

// ─── Submit (mirrors POST /v1/vendor-portal/submissions/{id}/submit) ─
export async function submitBid(submissionId: string): Promise<SubmitBidResult> {
  await delay(600);
  const result: SubmitBidResult = {
    id: submissionId,
    confirmation_number: `BID-${new Date().getFullYear()}-${String(
      Math.floor(Math.random() * 9000) + 1000,
    )}`,
    submitted_at: new Date().toISOString(),
  };
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] submitBid →', result);
  return result;
}

// ─── Attachment mocks (pure local state) ────────────────────────────
export async function uploadAttachment(file: File): Promise<FormAttachment> {
  await delay(400);
  const attachment: FormAttachment = {
    id: uid('att'),
    file,
    name: file.name,
    size: file.size,
    uploadedAt: new Date().toISOString(),
  };
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] uploadAttachment →', attachment.id, file.name);
  return attachment;
}

export async function deleteAttachment(id: string): Promise<void> {
  await delay(150);
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] deleteAttachment →', id);
}

// ─── Project document download stub ─────────────────────────────────
export async function downloadProjectDocument(documentId: string): Promise<string> {
  await delay(200);
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] downloadProjectDocument →', documentId);
  // In Task 5.3 this will return a signed URL from Supabase Storage.
  return `#mock-download/${documentId}`;
}
