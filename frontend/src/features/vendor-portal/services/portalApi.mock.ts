/**
 * Mock implementation of the vendor portal API.
 *
 * Preserved verbatim from the original Task 5.1 portalApi.ts so that
 * client demos, E2E tests, Storybook, and onboarding have a stable,
 * realistic in-memory backend to run against even after the real
 * FastAPI endpoints (Tasks 5.2–5.5) come online.
 *
 * Selection of mock vs. real is done by `portalApi.ts` via the
 * `VITE_DEMO_MODE` flag. Never import from this file directly.
 */

import axios from 'axios';
import type {
  BidDraft,
  FormAttachment,
  RevisionPrefillResponse,
  SubmissionAttachmentMeta,
  SubmitBidResult,
  ValidateTokenResponse,
  VendorBidContext,
} from '../types/portal';
import { PortalApiError } from '../types/portal';
import type {
  BidRevisionRequestResponse,
  DraftPayload,
  PortalApi,
} from './portalApi.types';

// ─── Axios instance (configured, but mocks bypass the network) ──────
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

const mockAxios = axios.create({
  baseURL: `${apiBaseUrl}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
});

// Kept so the interceptor wiring from Task 5.1 is preserved; mocks
// never actually fire requests through this instance.
void mockAxios;

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
 *   - `revision-token`   → happy path WITH revision_context populated
 * Any other token resolves to the happy-path context.
 */
async function validateToken(token: string): Promise<ValidateTokenResponse> {
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
    case 'revision-token': {
      const ctx = cloneContext(SEED_CONTEXT);
      ctx.revision_context = {
        bid_revision_request_id: 'rev-req-mock-001',
        pm_note:
          'Please revise the Cut and Fill unit price — the geotech report\nindicates more rock than originally scoped. Update line item 3.',
        // 18h from now → exercises the <24h countdown branch.
        revision_deadline: new Date(Date.now() + 18 * 60 * 60 * 1000).toISOString(),
        original_submission_id: 'sub-original-mock-001',
        original_revision_number: 1,
      };
      return { jwt: `mock.vendor.jwt.${uid('tok')}`, bid_context: ctx };
    }
    default:
      return {
        jwt: `mock.vendor.jwt.${uid('tok')}`,
        bid_context: cloneContext(SEED_CONTEXT),
      };
  }
}

// ─── Draft persistence ──────────────────────────────────────────────
async function createDraft(payload: DraftPayload): Promise<BidDraft> {
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

async function updateDraft(id: string, payload: DraftPayload): Promise<BidDraft> {
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
async function submitBid(submissionId: string): Promise<SubmitBidResult> {
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
// Signatures mirror the real backend: both take a submissionId so the UI
// code paths are identical in demo mode and prod.
async function uploadAttachment(
  submissionId: string,
  file: File,
): Promise<FormAttachment> {
  await delay(400);
  const attachment: FormAttachment = {
    id: uid('att'),
    file,
    name: file.name,
    size: file.size,
    uploadedAt: new Date().toISOString(),
  };
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] uploadAttachment →', submissionId, attachment.id, file.name);
  return attachment;
}

async function deleteAttachment(
  submissionId: string,
  attachmentId: string,
): Promise<void> {
  await delay(150);
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] deleteAttachment →', submissionId, attachmentId);
}

// ─── Revision prefill + attachment metadata (Phase E) ───────────────
async function getRevisionPrefill(
  originalSubmissionId: string,
): Promise<RevisionPrefillResponse> {
  await delay(400);
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] getRevisionPrefill →', originalSubmissionId);
  return {
    total_amount: '52800.0',
    vendor_notes: 'Original bid — mobilization quoted firm for 30 days.',
    line_items: SEED_CONTEXT.bid_template.items.map((it) => ({
      template_item_id: it.id,
      description: it.description,
      item_type: it.item_type,
      quantity: it.item_type === 'unit_price' ? '100.0' : null,
      unit_of_measure: it.unit_of_measure,
      unit_price: it.item_type === 'unit_price' ? '120.0' : null,
      lump_sum_amount: it.item_type === 'lump_sum' ? '8000.0' : null,
      line_total: it.item_type === 'lump_sum' ? '8000.0' : '12000.0',
      sort_order: it.sort_order,
    })),
    attachment_ids: ['att-orig-000', 'att-orig-001'],
  };
}

async function listSubmissionAttachments(
  submissionId: string,
): Promise<SubmissionAttachmentMeta[]> {
  await delay(200);
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] listSubmissionAttachments →', submissionId);
  return [
    {
      id: 'att-orig-000',
      file_name: 'Original_Bid_Proposal.pdf',
      file_size: 1_204_233,
      file_type: 'application/pdf',
      uploaded_at: new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: 'att-orig-001',
      file_name: 'Insurance_Certificate.pdf',
      file_size: 318_004,
      file_type: 'application/pdf',
      uploaded_at: new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString(),
    },
  ];
}

async function declineRevisionRequest(
  revisionRequestId: string,
  decline_reason?: string,
): Promise<BidRevisionRequestResponse> {
  await delay(300);
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] declineRevisionRequest →', revisionRequestId);
  const now = new Date().toISOString();
  const reason = decline_reason?.trim() || null;
  return {
    id: revisionRequestId,
    bid_invitation_id: 'inv-mock-001',
    original_submission_id: 'sub-original-mock-001',
    pm_note: 'Please revise the Cut and Fill unit price.',
    revision_deadline: new Date(Date.now() + 18 * 60 * 60 * 1000).toISOString(),
    status: 'declined',
    decline_reason: reason,
    requested_by: 'pm-mock-001',
    requested_at: now,
    responded_at: now,
    created_at: now,
    updated_at: now,
  };
}

// ─── Project document download stub ─────────────────────────────────
async function downloadProjectDocument(documentId: string): Promise<string> {
  await delay(200);
  // eslint-disable-next-line no-console
  console.log('[portalApi:mock] downloadProjectDocument →', documentId);
  // In Task 5.3 this will return a signed URL from Supabase Storage.
  return `#mock-download/${documentId}`;
}

export const mockPortalApi: PortalApi = {
  // Mock never hits the network, so JWT state is a no-op.
  setVendorJwt: () => {},
  getVendorJwt: () => null,
  // No 401s in mock mode — handler is accepted but never invoked. Keeping
  // the contract symmetric avoids type drift between impls.
  setAuthFailureHandler: () => {},
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
};
