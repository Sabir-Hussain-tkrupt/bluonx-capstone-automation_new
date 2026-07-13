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

// The mocked vendor company name is "Summit".
describe('Step4Review — SoW signature gate', () => {
  it('disables submit when the signature is empty', () => {
    renderReview('');
    expect(screen.getByRole('button', { name: 'Submit Bid' })).toBeDisabled();
  });

  it('disables submit when the signature does not match the company name', () => {
    renderReview('SUMMIT GRADING');
    expect(screen.getByRole('button', { name: 'Submit Bid' })).toBeDisabled();
  });

  it('enables submit when the signature matches (case-insensitive)', () => {
    renderReview('summit');
    expect(screen.getByRole('button', { name: 'Submit Bid' })).toBeEnabled();
  });

  it('tolerates surrounding / repeated whitespace', () => {
    renderReview('  SUMMIT  ');
    expect(screen.getByRole('button', { name: 'Submit Bid' })).toBeEnabled();
  });

  it('renders the signature as a read-back line', () => {
    renderReview('SUMMIT');
    expect(screen.getByText('Scope of Work attestation')).toBeInTheDocument();
    expect(screen.getByText('SUMMIT')).toBeInTheDocument();
  });
});
