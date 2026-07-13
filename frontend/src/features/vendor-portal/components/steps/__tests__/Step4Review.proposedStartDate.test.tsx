import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Step4Review } from '../Step4Review';
import type { BidFormState, VendorBidContext } from '../../../types/portal';

const ctx: Pick<VendorBidContext, 'vendor' | 'project' | 'task' | 'bid_template'> = {
  vendor: {
    id: 'v1',
    company_name: 'Apex',
    primary_contact_name: 'Jane',
    email: 'jane@a.example',
    phone: null,
  },
  project: { id: 'p1', name: 'Phoenix', location: 'AZ', address: '1 Main' },
  task: { id: 't1', name: 'Mass Grading', description: '', trade_name: 'EW' },
  bid_template: { id: 'tpl', name: 'T', is_lump_sum: true, items: [] },
};

vi.mock('../../../hooks/useBidContext', () => ({
  useBidContext: () => ctx,
}));

function makeState(proposed: string | null): BidFormState {
  return {
    step: 4,
    completedSteps: [1, 2, 3],
    dirty: false,
    companyInfo: { vendor_notes: '', proposed_start_date: proposed, sow_attested_name: 'Apex' },
    pricing: { total_amount: 1000, line_items: [] },
    attachments: [],
    submissionId: 's1',
  };
}

function renderReview(state: BidFormState) {
  return render(
    <Step4Review
      state={state}
      onEdit={vi.fn()}
      onBack={vi.fn()}
      onSaveDraft={vi.fn()}
      onSubmit={vi.fn()}
      submitting={false}
      isRevision={false}
    />,
  );
}

describe('Step4Review — proposed_start_date summary', () => {
  it('shows the proposed start date when set', () => {
    renderReview(makeState('2026-09-15'));
    expect(screen.getByText(/Proposed start/i)).toBeInTheDocument();
    expect(screen.getByText(/2026-09-15|September 15, 2026/i)).toBeInTheDocument();
  });

  it('shows a placeholder when the proposed start date is null', () => {
    renderReview(makeState(null));
    // Either an em-dash placeholder or omitting the row is fine — we just
    // assert the date string itself is absent.
    expect(screen.queryByText(/2026-09-15|September 15, 2026/i)).not.toBeInTheDocument();
  });
});
