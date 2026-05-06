import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { cloneElement, type ReactElement } from 'react';
import { BidAmountBarChart } from '../BidAmountBarChart';
import type { SubmittedBid } from '@/features/bids/types';

vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactElement }) => (
      <div style={{ width: 600, height: 300 }}>
        {cloneElement(children, { width: 600, height: 300 } as Record<string, unknown>)}
      </div>
    ),
  };
});

describe('BidAmountBarChart', () => {
  it('returns null when submittedBids is empty', () => {
    const { container } = render(<BidAmountBarChart submittedBids={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders an SVG with one bar per vendor when bids exist', () => {
    const bids: SubmittedBid[] = [
      { vendor_company_name: 'Bedrock Civil', total_amount: 41200 },
      { vendor_company_name: 'Apex Grading', total_amount: 47500 },
    ];

    const { getByText, container } = render(<BidAmountBarChart submittedBids={bids} />);

    expect(getByText('Submitted Bid Amounts')).toBeInTheDocument();
    expect(container.querySelector('svg')).not.toBeNull();

    const bars = container.querySelectorAll('.recharts-bar-rectangle');
    expect(bars.length).toBe(bids.length);
  });
});
