import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RevisionDeadline } from '../RevisionDeadline';

describe('RevisionDeadline', () => {
  it('shows a prominent countdown when the deadline is within 24h', () => {
    const in18h = new Date(Date.now() + 18 * 60 * 60 * 1000).toISOString();
    render(<RevisionDeadline deadline={in18h} />);
    expect(screen.getByText(/Revision due in/i)).toBeInTheDocument();
    expect(screen.getByText(/\d+h \d+m/)).toBeInTheDocument();
  });

  it('shows a relative date when the deadline is more than 24h away', () => {
    const in3d = new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString();
    render(<RevisionDeadline deadline={in3d} />);
    expect(screen.getByText(/^Due/)).toBeInTheDocument();
    expect(screen.queryByText(/Revision due in/i)).toBeNull();
  });

  it('reports a passed deadline', () => {
    const past = new Date(Date.now() - 60_000).toISOString();
    render(<RevisionDeadline deadline={past} />);
    expect(
      screen.getByText(/revision deadline has passed/i),
    ).toBeInTheDocument();
  });
});
