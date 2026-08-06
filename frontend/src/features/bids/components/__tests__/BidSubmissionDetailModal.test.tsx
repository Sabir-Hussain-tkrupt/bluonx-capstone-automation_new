import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { BidSubmissionDetailModal } from '../BidSubmissionDetailModal';
import type { BidSubmissionDetail } from '@/features/bids/types';
import {
  makeBidSubmissionAttachment,
  makeBidSubmissionDetail,
  makeBidSubmissionLineItem,
} from '@/features/bids/test/fixtures';

const mockUseBidSubmissionDetail = vi.fn();

vi.mock('@/features/bids/hooks/useBidSubmissionDetail', () => ({
  useBidSubmissionDetail: (id: string | null) => mockUseBidSubmissionDetail(id),
}));

// A fully populated submission — the shared builder owns the field list, this
// wrapper adds only the pricing/notes/attachments this file asserts on.
function makeDetail(overrides: Partial<BidSubmissionDetail> = {}): BidSubmissionDetail {
  return makeBidSubmissionDetail({
    total_amount: 47500,
    vendor_notes: 'Includes mobilization.',
    vendor_company_name: 'Apex Grading',
    vendor_contact_name: 'Jane Roe',
    vendor_contact_email: 'jane@apex.example.com',
    line_items: [
      makeBidSubmissionLineItem({
        id: 'li-1',
        description: 'Site prep',
        lump_sum_amount: 12500,
        line_total: 12500,
      }),
      makeBidSubmissionLineItem({
        id: 'li-2',
        description: 'Excavation',
        item_type: 'unit_price',
        quantity: 300,
        unit_of_measure: 'CY',
        unit_price: 100,
        lump_sum_amount: null,
        line_total: 30000,
        sort_order: 1,
      }),
    ],
    attachments: [makeBidSubmissionAttachment()],
    ...overrides,
  });
}

describe('BidSubmissionDetailModal', () => {
  beforeEach(() => {
    mockUseBidSubmissionDetail.mockReset();
  });

  it('shows a skeleton while loading', () => {
    mockUseBidSubmissionDetail.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    });

    renderWithRouter(
      <BidSubmissionDetailModal submissionId="sub-1" isOpen onClose={() => {}} />,
    );

    expect(screen.getByTestId('bid-detail-skeleton')).toBeInTheDocument();
  });

  it('renders header, total, line items, notes and attachments', () => {
    mockUseBidSubmissionDetail.mockReturnValue({
      data: makeDetail(),
      isLoading: false,
      error: null,
    });

    renderWithRouter(
      <BidSubmissionDetailModal submissionId="sub-1" isOpen onClose={() => {}} />,
    );

    expect(screen.getByText('Apex Grading')).toBeInTheDocument();
    // Total Bid in header — value also appears in Grand Total footer when sums match,
    // so allow ≥1 occurrence.
    expect(screen.getAllByText('$47,500').length).toBeGreaterThan(0);
    // Each line item appears in both mobile + desktop layouts, so use getAllByText.
    expect(screen.getAllByText('Site prep').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Excavation').length).toBeGreaterThan(0);

    // New columns: Type badge + Grand Total footer (rendered in mobile + desktop)
    expect(screen.getAllByText('Lump Sum').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Unit Price').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Grand Total').length).toBeGreaterThan(0);

    // Notes section
    expect(screen.getByText('Vendor Notes')).toBeInTheDocument();
    expect(screen.getByText('Includes mobilization.')).toBeInTheDocument();

    // Attachments
    expect(screen.getByText('Attachments')).toBeInTheDocument();
    expect(screen.getByText('scope.pdf')).toBeInTheDocument();
    const downloadLink = screen.getByRole('link', { name: 'Download' });
    expect(downloadLink).toHaveAttribute(
      'href',
      'https://signed.example.com/scope.pdf?token=abc',
    );
    expect(downloadLink).toHaveAttribute('target', '_blank');
    expect(downloadLink).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('hides Vendor Notes section when notes are empty', () => {
    mockUseBidSubmissionDetail.mockReturnValue({
      data: makeDetail({ vendor_notes: null }),
      isLoading: false,
      error: null,
    });

    renderWithRouter(
      <BidSubmissionDetailModal submissionId="sub-1" isOpen onClose={() => {}} />,
    );

    expect(screen.queryByText('Vendor Notes')).toBeNull();
  });

  it('hides Attachments section when there are none', () => {
    mockUseBidSubmissionDetail.mockReturnValue({
      data: makeDetail({ attachments: [] }),
      isLoading: false,
      error: null,
    });

    renderWithRouter(
      <BidSubmissionDetailModal submissionId="sub-1" isOpen onClose={() => {}} />,
    );

    expect(screen.queryByText('Attachments')).toBeNull();
  });

  it('shows the proposed start date in both the header and the total block', () => {
    mockUseBidSubmissionDetail.mockReturnValue({
      data: makeDetail({ proposed_start_date: '2026-09-15' }),
      isLoading: false,
      error: null,
    });

    renderWithRouter(
      <BidSubmissionDetailModal submissionId="sub-1" isOpen onClose={() => {}} />,
    );

    // Formatted by formatDateOnly, which parses the parts rather than going
    // through `new Date(string)` so the day cannot slip in a negative-offset zone.
    expect(screen.getByText(/Proposed start Sep 15, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/Start: Sep 15, 2026/)).toBeInTheDocument();
  });

  it('omits the proposed start date entirely when the vendor gave none', () => {
    mockUseBidSubmissionDetail.mockReturnValue({
      data: makeDetail({ proposed_start_date: null }),
      isLoading: false,
      error: null,
    });

    renderWithRouter(
      <BidSubmissionDetailModal submissionId="sub-1" isOpen onClose={() => {}} />,
    );

    // Not an em dash placeholder from formatDateOnly — the rows are not rendered.
    expect(screen.queryByText(/Proposed start/)).toBeNull();
    expect(screen.queryByText(/Start:/)).toBeNull();
  });

  it('shows the Direct Assign pill when is_direct_assign is true', () => {
    mockUseBidSubmissionDetail.mockReturnValue({
      data: makeDetail({ is_direct_assign: true }),
      isLoading: false,
      error: null,
    });

    renderWithRouter(
      <BidSubmissionDetailModal submissionId="sub-1" isOpen onClose={() => {}} />,
    );

    expect(screen.getByText('Direct Assign')).toBeInTheDocument();
  });
});
