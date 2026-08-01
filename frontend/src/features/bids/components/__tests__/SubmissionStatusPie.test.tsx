import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { cloneElement, type ReactElement } from 'react';
import { SubmissionStatusPie } from '../SubmissionStatusPie';
import type { InvitationSummary } from '@/features/bids/types';

// Recharts' ResponsiveContainer measures parent box, which JSDOM reports as 0×0
// and the chart will not render. Stub it to a fixed-size div so child charts paint.
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactElement }) => (
      <div style={{ width: 400, height: 220 }}>
        {cloneElement(children, { width: 400, height: 220 } as Record<string, unknown>)}
      </div>
    ),
  };
});

function makeSummary(overrides: Partial<InvitationSummary> = {}): InvitationSummary {
  return {
    total: 0,
    sent: 0,
    opened: 0,
    submitted: 0,
    declined: 0,
    expired: 0,
    no_response: 0,
    ...overrides,
  };
}

describe('SubmissionStatusPie', () => {
  it('renders nothing when total is 0', () => {
    const { container } = render(
      <SubmissionStatusPie summary={makeSummary({ total: 0 })} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders the chart heading and an SVG when invitations exist', () => {
    const { getByText, container } = render(
      <SubmissionStatusPie
        summary={makeSummary({ total: 3, sent: 1, opened: 1, submitted: 1 })}
      />,
    );

    expect(getByText('Invitation Status')).toBeInTheDocument();
    expect(container.querySelector('svg')).not.toBeNull();
  });

  it('skips empty slices (only renders legend entries for non-zero statuses)', () => {
    const { container, queryByText } = render(
      <SubmissionStatusPie
        summary={makeSummary({ total: 2, submitted: 1, expired: 1 })}
      />,
    );

    // Legend should list only the two non-zero statuses (Submitted, Expired)
    // and skip Sent / Opened / Declined.
    const legendItems = container.querySelectorAll('.recharts-legend-item');
    expect(legendItems.length).toBe(2);
    expect(queryByText('Submitted')).toBeInTheDocument();
    expect(queryByText('Expired')).toBeInTheDocument();
    expect(queryByText('Sent')).toBeNull();
    expect(queryByText('Opened')).toBeNull();
    expect(queryByText('Declined')).toBeNull();
  });

  it('renders a No Response slice when present', () => {
    const { container, queryByText } = render(
      <SubmissionStatusPie
        summary={makeSummary({ total: 2, submitted: 1, no_response: 1 })}
      />,
    );

    const legendItems = container.querySelectorAll('.recharts-legend-item');
    expect(legendItems.length).toBe(2);
    expect(queryByText('Submitted')).toBeInTheDocument();
    expect(queryByText('No Response')).toBeInTheDocument();
  });
});
