import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { SubmissionConfirmationPage } from '../SubmissionConfirmationPage';

vi.mock('../../hooks/useBidContext', () => ({
  useBidContext: () => ({
    vendor: { primary_contact_name: 'Marcus', email: 'm@x.com' },
    project: { name: 'Phoenix Park' },
    task: { name: 'Grading' },
  }),
}));

const result = {
  id: 'sub-1',
  submitted_at: new Date().toISOString(),
  total_amount: '50800.0',
};

describe('SubmissionConfirmationPage', () => {
  it('renders the revision heading and statement when state.isRevision is true', () => {
    renderWithRouter(<SubmissionConfirmationPage />, {
      initialEntries: [
        {
          pathname: '/bid/submitted/sub-1',
          state: { result, grandTotal: 50800, isRevision: true },
        },
      ],
    });

    expect(screen.getByText('Revised Bid Submitted')).toBeInTheDocument();
    expect(
      screen.getByText(/your original bid remains in the record/i),
    ).toBeInTheDocument();
  });

  it('renders the standard heading for an initial submission', () => {
    renderWithRouter(<SubmissionConfirmationPage />, {
      initialEntries: [
        {
          pathname: '/bid/submitted/sub-1',
          state: { result, grandTotal: 50800 },
        },
      ],
    });

    expect(
      screen.getByText('Bid submitted successfully'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Revised Bid Submitted')).toBeNull();
  });
});
