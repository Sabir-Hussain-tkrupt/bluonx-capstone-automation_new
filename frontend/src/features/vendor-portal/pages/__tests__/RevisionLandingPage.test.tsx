import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { RevisionLandingPage } from '../RevisionLandingPage';
import type { VendorBidContext } from '../../types/portal';

const navigateMock = vi.fn();

vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
}));

const ctxHolder = vi.hoisted(() => ({ current: null as VendorBidContext | null }));
vi.mock('../../hooks/useBidContext', () => ({
  useBidContext: () => ctxHolder.current,
}));

function baseContext(
  revision: VendorBidContext['revision_context'],
): VendorBidContext {
  return {
    vendor: {
      id: 'v1',
      company_name: 'Summit Earthworks',
      primary_contact_name: 'Marcus',
      email: 'm@x.com',
      phone: null,
    },
    project: { id: 'p1', name: 'Phoenix Park', location: 'AZ', address: 'addr' },
    task: { id: 't1', name: 'Grading', description: '', trade_name: 'Earthwork' },
    bid_package: { id: 'bp1', round_number: 1, deadline: '', instructions: '' },
    bid_template: { id: 'tpl', name: 'T', is_lump_sum: false, items: [] },
    project_documents: [],
    existing_draft: null,
    revision_context: revision,
  };
}

describe('RevisionLandingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the PM note and deadline when revision_context is present', () => {
    ctxHolder.current = baseContext({
      bid_revision_request_id: 'rr1',
      pm_note: 'Please revise line item 3.',
      revision_deadline: new Date(Date.now() + 3 * 86400000).toISOString(),
      original_submission_id: 'sub1',
      original_revision_number: 1,
    });
    renderWithRouter(<RevisionLandingPage />);

    expect(screen.getByText('Revision Requested')).toBeInTheDocument();
    expect(screen.getByText('Please revise line item 3.')).toBeInTheDocument();
    expect(screen.getByText(/^Due/)).toBeInTheDocument();
  });

  it('navigates to the bid form when "Open Bid Form" is clicked', async () => {
    ctxHolder.current = baseContext({
      bid_revision_request_id: 'rr1',
      pm_note: 'note',
      revision_deadline: new Date(Date.now() + 3 * 86400000).toISOString(),
      original_submission_id: 'sub1',
      original_revision_number: 1,
    });
    const user = userEvent.setup();
    renderWithRouter(<RevisionLandingPage />);

    await user.click(screen.getByRole('button', { name: /open bid form/i }));
    expect(navigateMock).toHaveBeenCalledWith('/bid/form');
  });
});
