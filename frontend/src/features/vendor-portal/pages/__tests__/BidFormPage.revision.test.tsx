import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { BidFormPage } from '../BidFormPage';
import type { VendorBidContext } from '../../types/portal';

const getRevisionPrefill = vi.fn();
const listSubmissionAttachments = vi.fn();

vi.mock('@/features/vendor-portal/services/portalApi', () => ({
  createDraft: vi.fn(),
  updateDraft: vi.fn(),
  submitBid: vi.fn(),
  getRevisionPrefill: (...a: unknown[]) => getRevisionPrefill(...a),
  listSubmissionAttachments: (...a: unknown[]) =>
    listSubmissionAttachments(...a),
}));

const ctxHolder = vi.hoisted(() => ({ current: null as VendorBidContext | null }));
vi.mock('@/features/vendor-portal/hooks/useBidContext', () => ({
  useBidContext: () => ctxHolder.current,
}));

function baseContext(
  revision: VendorBidContext['revision_context'],
): VendorBidContext {
  return {
    vendor: {
      id: 'v1',
      company_name: 'Summit',
      primary_contact_name: 'Marcus',
      email: 'm@x.com',
      phone: null,
    },
    project: { id: 'p1', name: 'Phoenix', location: 'AZ', address: 'a' },
    task: { id: 't1', name: 'Grading', description: '', trade_name: 'EW' },
    bid_package: {
      id: 'bp1',
      round_number: 1,
      deadline: new Date(Date.now() + 7 * 86400000).toISOString(),
      instructions: '',
    },
    bid_template: { id: 'tpl', name: 'T', is_lump_sum: true, items: [] },
    project_documents: [],
    existing_draft: null,
    revision_context: revision,
  };
}

describe('BidFormPage revision mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getRevisionPrefill.mockResolvedValue({
      total_amount: '52800.0',
      vendor_notes: 'orig notes',
      line_items: [],
      attachment_ids: [],
    });
    listSubmissionAttachments.mockResolvedValue([]);
  });

  it('shows the revision banner with the PM note when revision_context is present', async () => {
    ctxHolder.current = baseContext({
      bid_revision_request_id: 'rr1',
      pm_note: 'Revise the cut and fill price.',
      revision_deadline: new Date(Date.now() + 86400000).toISOString(),
      original_submission_id: 'sub-orig-1',
      original_revision_number: 1,
    });

    renderWithRouter(<BidFormPage />);

    expect(
      await screen.findByText(
        /You are submitting a revision\. Your original bid is preserved\./i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Revise the cut and fill price.'),
    ).toBeInTheDocument();
    expect(getRevisionPrefill).toHaveBeenCalledWith('sub-orig-1');
  });

  it('does not show the revision banner in initial-bid mode', () => {
    ctxHolder.current = baseContext(null);
    renderWithRouter(<BidFormPage />);

    expect(
      screen.queryByText(/You are submitting a revision/i),
    ).toBeNull();
    expect(getRevisionPrefill).not.toHaveBeenCalled();
  });
});
