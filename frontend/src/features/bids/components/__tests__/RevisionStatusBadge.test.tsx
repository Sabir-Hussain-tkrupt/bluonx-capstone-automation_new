import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RevisionStatusBadge } from '../RevisionStatusBadge';
import type { RevisionRequestStatus } from '@/features/bids/types';

describe('RevisionStatusBadge', () => {
  it('renders the correct label for each non-cancelled status', () => {
    const cases: Array<[RevisionRequestStatus, string]> = [
      ['pending', 'Revision Pending'],
      ['submitted', 'Revised'],
      ['declined', 'Declined'],
      ['expired', 'Expired'],
    ];
    for (const [status, label] of cases) {
      const { unmount } = render(<RevisionStatusBadge status={status} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      unmount();
    }
  });

  it('renders nothing for cancelled', () => {
    const { container } = render(<RevisionStatusBadge status="cancelled" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('exposes the decline reason as a tooltip when declined', () => {
    render(
      <RevisionStatusBadge status="declined" declineReason="Scope too small" />,
    );
    expect(screen.getByText('Declined')).toHaveAttribute(
      'title',
      'Scope too small',
    );
  });
});
