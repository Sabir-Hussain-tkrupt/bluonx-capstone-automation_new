import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Step4Review } from '../Step4Review';
import type { BidFormState, VendorBidContext } from '../../../types/portal';

const ctx: Pick<VendorBidContext, 'vendor' | 'project' | 'task' | 'bid_template'> =
  {
    vendor: {
      id: 'v1',
      company_name: 'Summit',
      primary_contact_name: 'Marcus',
      email: 'm@x.com',
      phone: null,
    },
    project: { id: 'p1', name: 'Phoenix', location: 'AZ', address: 'a' },
    task: { id: 't1', name: 'Grading', description: '', trade_name: 'EW' },
    bid_template: { id: 'tpl', name: 'T', is_lump_sum: true, items: [] },
  };

vi.mock('../../../hooks/useBidContext', () => ({
  useBidContext: () => ctx,
}));

const state: BidFormState = {
  step: 4,
  completedSteps: [1, 2, 3],
  dirty: false,
  companyInfo: { vendor_notes: '' },
  pricing: { total_amount: 1000, line_items: [] },
  attachments: [],
  submissionId: 's1',
};

function renderReview(isRevision: boolean) {
  return render(
    <Step4Review
      state={state}
      onEdit={vi.fn()}
      onBack={vi.fn()}
      onSaveDraft={vi.fn()}
      onSubmit={vi.fn()}
      submitting={false}
      isRevision={isRevision}
    />,
  );
}

describe('Step4Review submit label', () => {
  it('reads "Submit Bid" in initial mode', () => {
    renderReview(false);
    expect(
      screen.getByRole('button', { name: 'Submit Bid' }),
    ).toBeInTheDocument();
  });

  it('reads "Submit Revised Bid" in revision mode', () => {
    renderReview(true);
    expect(
      screen.getByRole('button', { name: 'Submit Revised Bid' }),
    ).toBeInTheDocument();
  });
});
