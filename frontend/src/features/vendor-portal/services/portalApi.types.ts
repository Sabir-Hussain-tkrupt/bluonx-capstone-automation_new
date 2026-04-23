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
  SubmitBidResult,
  ValidateTokenResponse,
} from '../types/portal';

export interface DraftPayload {
  vendor_notes: string;
  total_amount: number | null;
  line_items: BidDraftLineItem[];
  attachment_ids: string[];
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
}
