/**
 * Shared test fixtures for the bids feature.
 *
 * These builders own the *complete* field list for their type. Tests should
 * extend them with overrides rather than hand-rolling a literal: when a field
 * is added to the type, exactly one file needs updating and the failure is a
 * clear "property missing" here, instead of the same field going stale in
 * three separate test files at once.
 */
import type {
  BidSubmissionAttachment,
  BidSubmissionDetail,
  BidSubmissionLineItem,
  InvitationSummary,
} from '@/features/bids/types';

export function makeBidSubmissionLineItem(
  overrides: Partial<BidSubmissionLineItem> = {},
): BidSubmissionLineItem {
  return {
    id: 'li-1',
    description: 'Site prep',
    item_type: 'lump_sum',
    quantity: null,
    unit_of_measure: null,
    unit_price: null,
    lump_sum_amount: 1000,
    line_total: 1000,
    sort_order: 0,
    ...overrides,
  };
}

export function makeBidSubmissionAttachment(
  overrides: Partial<BidSubmissionAttachment> = {},
): BidSubmissionAttachment {
  return {
    id: 'a-1',
    file_name: 'scope.pdf',
    file_size: 12345,
    file_type: 'application/pdf',
    uploaded_at: '2026-05-01T12:00:00Z',
    download_url: 'https://signed.example.com/scope.pdf?token=abc',
    download_url_expires_in: 3600,
    ...overrides,
  };
}

/**
 * A submitted, non-draft, first-round bid with no line items or attachments.
 * Tests that care about pricing or files pass their own arrays.
 */
export function makeBidSubmissionDetail(
  overrides: Partial<BidSubmissionDetail> = {},
): BidSubmissionDetail {
  return {
    id: 'sub-1',
    bid_invitation_id: 'inv-1',
    status: 'submitted',
    is_direct_assign: false,
    is_draft: false,
    is_superseded: false,
    revision_number: 1,
    supersedes_submission_id: null,
    total_amount: 1000,
    vendor_notes: null,
    submitted_at: '2026-05-01T12:00:00Z',
    proposed_start_date: null,
    vendor_company_name: 'Apex',
    vendor_contact_name: null,
    vendor_contact_email: null,
    line_items: [],
    attachments: [],
    ...overrides,
  };
}

/** An all-zero invitation summary; tests set only the counts they exercise. */
export function makeInvitationSummary(
  overrides: Partial<InvitationSummary> = {},
): InvitationSummary {
  return {
    total: 0,
    pending_send: 0,
    sent: 0,
    send_failed: 0,
    opened: 0,
    submitted: 0,
    declined: 0,
    expired: 0,
    no_response: 0,
    ...overrides,
  };
}
