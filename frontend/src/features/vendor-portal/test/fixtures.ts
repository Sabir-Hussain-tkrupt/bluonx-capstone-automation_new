/**
 * Shared test fixtures for the vendor portal.
 *
 * These builders own the *complete* field list for their type. Tests extend
 * them with overrides rather than hand-rolling a literal: when a field is
 * added to the type, exactly one file needs updating instead of the same
 * field going stale across four or five test files at once.
 *
 * Kept inside the portal feature on purpose. The vendor portal is an isolated
 * subsystem (see CLAUDE.md), so its fixtures do not belong in a shared
 * top-level module next to the admin ones.
 */
import type {
  BidDraft,
  PortalBidPackage,
  PortalBidTemplate,
  PortalVendor,
  RevisionPrefillLineItem,
  VendorBidContext,
} from '../types/portal';

/**
 * Note for SoW tests: the attestation must match `company_name`, so a test
 * that signs by typing a name has to set this explicitly rather than rely on
 * the default.
 */
export function makePortalVendor(overrides: Partial<PortalVendor> = {}): PortalVendor {
  return {
    id: 'v1',
    company_name: 'Summit Earthworks',
    primary_contact_name: 'Marcus',
    email: 'm@x.com',
    phone: null,
    ...overrides,
  };
}

export function makePortalBidPackage(
  overrides: Partial<PortalBidPackage> = {},
): PortalBidPackage {
  return {
    id: 'bp1',
    round_number: 1,
    deadline: '2026-09-01T17:00:00Z',
    instructions: '',
    desired_start_date: null,
    scope_of_work_document_id: null,
    scope_of_work_file_name: null,
    ...overrides,
  };
}

/** A lump-sum template with no line items; pricing tests supply their own. */
export function makePortalBidTemplate(
  overrides: Partial<PortalBidTemplate> = {},
): PortalBidTemplate {
  return {
    id: 'tpl',
    name: 'Lump sum',
    is_lump_sum: true,
    items: [],
    ...overrides,
  };
}

/**
 * An initial-bid context: no existing draft, no revision. Tests needing a
 * custom package compose the builders, e.g.
 * `makeVendorBidContext({ bid_package: makePortalBidPackage({ desired_start_date: '2026-09-01' }) })`.
 */
export function makeVendorBidContext(
  overrides: Partial<VendorBidContext> = {},
): VendorBidContext {
  return {
    vendor: makePortalVendor(),
    project: { id: 'p1', name: 'Phoenix Park', location: 'AZ', address: '1 Main' },
    task: { id: 't1', name: 'Grading', description: '', trade_name: 'Earthwork' },
    bid_package: makePortalBidPackage(),
    bid_template: makePortalBidTemplate(),
    project_documents: [],
    existing_draft: null,
    revision_context: null,
    ...overrides,
  };
}

/**
 * One line of a revision prefill, in wire shape: every numeric field is a
 * string (Pydantic Decimal) or null.
 */
export function makeRevisionPrefillLineItem(
  overrides: Partial<RevisionPrefillLineItem> = {},
): RevisionPrefillLineItem {
  return {
    template_item_id: 'ti-1',
    description: 'Site prep',
    item_type: 'lump_sum',
    quantity: null,
    unit_of_measure: null,
    unit_price: null,
    lump_sum_amount: null,
    line_total: null,
    sort_order: 0,
    ...overrides,
  };
}

export function makeBidDraft(overrides: Partial<BidDraft> = {}): BidDraft {
  return {
    id: 'draft-1',
    vendor_notes: '',
    total_amount: null,
    line_items: [],
    attachment_ids: [],
    last_saved_at: '2026-06-04T00:00:00Z',
    proposed_start_date: null,
    sow_attested_name: null,
    ...overrides,
  };
}
