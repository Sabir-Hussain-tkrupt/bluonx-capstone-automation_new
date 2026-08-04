import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CancelledPackageNotice } from '../CancelledPackageNotice';

describe('CancelledPackageNotice', () => {
  it('names who cancelled the round and when', () => {
    render(
      <CancelledPackageNotice
        cancelledAt="2026-08-03T10:00:00Z"
        cancelledByName="Jane Roe"
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent(
      /cancelled by Jane Roe on Aug 3, 2026/i,
    );
  });

  it('falls back to the date alone when the name is unavailable', () => {
    // cancelled_by is ON DELETE SET NULL and users are soft-deleted, so the
    // name can vanish while the date remains.
    render(
      <CancelledPackageNotice
        cancelledAt="2026-08-03T10:00:00Z"
        cancelledByName={null}
      />,
    );

    const notice = screen.getByRole('status');
    expect(notice).toHaveTextContent(/cancelled.*on Aug 3, 2026/i);
    expect(notice).not.toHaveTextContent(/ by /i);
  });

  it('explains that submitted bids survive but are no longer awardable', () => {
    render(
      <CancelledPackageNotice
        cancelledAt="2026-08-03T10:00:00Z"
        cancelledByName="Jane Roe"
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent(
      /no longer be awarded/i,
    );
  });

  it('renders nothing without a cancellation date', () => {
    const { container } = render(
      <CancelledPackageNotice cancelledAt={null} cancelledByName={null} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
