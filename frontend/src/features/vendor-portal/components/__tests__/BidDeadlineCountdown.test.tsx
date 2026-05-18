import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BidDeadlineCountdown } from '../BidDeadlineCountdown';

const PACKAGE_DEADLINE = new Date(Date.now() + 5 * 86400000).toISOString();
const REVISION_DEADLINE = new Date(Date.now() + 18 * 3600000).toISOString();

describe('BidDeadlineCountdown', () => {
  it('shows the package deadline with the default "Bid deadline" label (initial mode)', () => {
    render(<BidDeadlineCountdown deadline={PACKAGE_DEADLINE} />);
    expect(screen.getByText('Bid deadline')).toBeInTheDocument();
    expect(
      screen.getByText(
        `Due ${new Date(PACKAGE_DEADLINE).toLocaleString()}`,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('Revision deadline')).toBeNull();
  });

  it('shows the revision deadline with a "Revision deadline" label (revision mode)', () => {
    render(
      <BidDeadlineCountdown
        deadline={REVISION_DEADLINE}
        label="Revision deadline"
      />,
    );
    expect(screen.getByText('Revision deadline')).toBeInTheDocument();
    expect(
      screen.getByText(
        `Due ${new Date(REVISION_DEADLINE).toLocaleString()}`,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('Bid deadline')).toBeNull();
  });
});
