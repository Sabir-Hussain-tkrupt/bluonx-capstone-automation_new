/**
 * Shared contract for the vendor portal API layer.
 *
 * Both `portalApi.mock.ts` and `portalApi.real.ts` implement this
 * interface. If the real implementation adds, removes, or changes a
 * method, the mock will fail to compile until it is updated too —
 * this is the drift-prevention safety net for the demo-mode split.
 */

import type {
  BidDraft,
  BidDraftLineItem,
  FormAttachment,
  MilestoneRespondResult,
  MilestoneValidateResponse,
  RevisionPrefillResponse,
  SubmissionAttachmentMeta,
  SubmitBidResult,
  ValidateTokenResponse,
} from '../types/portal';

export interface DraftPayload {
  vendor_notes: string;
  total_amount: number | null;
  line_items: BidDraftLineItem[];
  attachment_ids: string[];
  /** Vendor's proposed start date (Task 8.1.5). ISO date string or null. */
  proposed_start_date: string | null;
  /** Vendor's typed CAPS SoW attestation. Empty until typed. */
  sow_attested_name: string | null;
}

/**
 * Mirrors the backend BidRevisionRequestResponse. Defined locally — the
 * vendor portal is an isolated subsystem and must not import from
 * `features/bids`. The decline flow only needs the call to resolve/reject,
 * so this is the minimal accurate shape.
 */
export interface BidRevisionRequestResponse {
  id: string;
  bid_invitation_id: string;
  original_submission_id: string;
  pm_note: string;
  revision_deadline: string;
  status: string;
  decline_reason: string | null;
  requested_by: string;
  requested_at: string;
  responded_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PortalApi {
  setVendorJwt: (token: string | null) => void;
  getVendorJwt: () => string | null;
  setAuthFailureHandler: (fn: (() => void) | null) => void;
  validateToken: (token: string) => Promise<ValidateTokenResponse>;
  createDraft: (payload: DraftPayload) => Promise<BidDraft>;
  updateDraft: (id: string, payload: DraftPayload) => Promise<BidDraft>;
  submitBid: (submissionId: string) => Promise<SubmitBidResult>;
  uploadAttachment: (submissionId: string, file: File) => Promise<FormAttachment>;
  deleteAttachment: (submissionId: string, attachmentId: string) => Promise<void>;
  downloadProjectDocument: (documentId: string) => Promise<string>;
  /** Original submission's data for revision-form prefill (revision tokens only). */
  getRevisionPrefill: (originalSubmissionId: string) => Promise<RevisionPrefillResponse>;
  /** Attachment metadata for a submission (resolves prefill attachment_ids). */
  listSubmissionAttachments: (
    submissionId: string,
  ) => Promise<SubmissionAttachmentMeta[]>;
  /** Vendor declines a pending revision request (revision tokens only). */
  declineRevisionRequest: (
    revisionRequestId: string,
    decline_reason?: string,
  ) => Promise<BidRevisionRequestResponse>;
  /** Validate a milestone check-in magic link → JWT + context or recorded answer. */
  validateMilestoneToken: (token: string) => Promise<MilestoneValidateResponse>;
  /** Record a Yes/No answer to a milestone check-in (milestone tokens only). */
  respondToMilestone: (
    milestoneAlertId: string,
    value: 'yes' | 'no',
  ) => Promise<MilestoneRespondResult>;
}
