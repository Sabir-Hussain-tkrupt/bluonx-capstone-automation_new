import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Step4Review } from '../Step4Review';
import type { BidFormState, VendorBidContext } from '../../../types/portal';

const ctx: Pick<VendorBidContext, 'vendor' | 'project' | 'task' | 'bid_template'> = {
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

function makeState(sow_attested_name: string): BidFormState {
  return {
    step: 4,
    completedSteps: [1, 2, 3],
    dirty: false,
    companyInfo: { vendor_notes: '', proposed_start_date: null, sow_attested_name },
    pricing: { total_amount: 1000, line_items: [] },
    attachments: [],
    submissionId: 's1',
  };
}

function renderReview(sow_attested_name: string) {
  return render(
    <Step4Review
      state={makeState(sow_attested_name)}
      onEdit={vi.fn()}
      onBack={vi.fn()}
      onSaveDraft={vi.fn()}
      onSubmit={vi.fn()}
      submitting={false}
    />,
  );
}

describe('Step4Review — SoW attestation gate', () => {
  it('disables submit when attestation is empty', () => {
    renderReview('');
    expect(screen.getByRole('button', { name: 'Submit Bid' })).toBeDisabled();
  });

  it('disables submit when attestation is not all-caps', () => {
    renderReview('Summit Grading');
    expect(screen.getByRole('button', { name: 'Submit Bid' })).toBeDisabled();
  });

  it('enables submit when a valid CAPS attestation is present', () => {
    renderReview('SUMMIT GRADING');
    expect(screen.getByRole('button', { name: 'Submit Bid' })).toBeEnabled();
  });

  it('renders the attestation as a read-back line', () => {
    renderReview('SUMMIT GRADING');
    expect(screen.getByText('Scope of Work attestation')).toBeInTheDocument();
    expect(screen.getByText('SUMMIT GRADING')).toBeInTheDocument();
  });
});
