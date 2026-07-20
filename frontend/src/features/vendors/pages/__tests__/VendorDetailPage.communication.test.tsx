/**
 * Task 7.7 — Communication tab on VendorDetailPage.
 *
 * Verifies the new Communication tab: label includes the email-log count,
 * and switching to it renders the shared EmailLogTable rows from the
 * vendor-scoped email-log endpoint.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { Routes, Route } from 'react-router-dom';

// ── Hook mocks ───────────────────────────────────────────────────────────
// All hooks VendorDetailPage consumes — page renders nothing real until
// useVendor returns data, so we stub every dependency.

const noop = vi.fn();

const useVendorMock = vi.fn();
const useVendorEmailLogMock = vi.fn();
const useVendorDocumentDownloadMock = vi.fn(() => ({
  download: noop,
  downloadingId: null,
}));

vi.mock('@/features/vendors/hooks/useVendor', () => ({
  useVendor: () => useVendorMock(),
}));
vi.mock('@/features/vendors/hooks/useVendorEmailLog', () => ({
  useVendorEmailLog: (id: string, enabled: boolean) =>
    useVendorEmailLogMock(id, enabled),
}));
vi.mock('@/features/vendors/hooks/useUpdateVendor', () => ({
  useUpdateVendor: () => ({ mutate: noop, isPending: false }),
}));
vi.mock('@/features/vendors/hooks/useDeleteVendor', () => ({
  useDeleteVendor: () => ({ mutate: noop, isPending: false }),
}));
vi.mock('@/features/vendors/hooks/useVendorContacts', () => ({
  useCreateContact: () => ({ mutate: noop, isPending: false }),
  useUpdateContact: () => ({ mutate: noop, isPending: false }),
  useDeleteContact: () => ({ mutate: noop, isPending: false }),
}));
vi.mock('@/features/vendors/hooks/useVendorTrades', () => ({
  useAddVendorTrades: () => ({ mutate: noop, isPending: false }),
  useRemoveVendorTrade: () => ({ mutate: noop, isPending: false }),
}));
vi.mock('@/features/vendors/hooks/useVendorDocuments', () => ({
  useDeleteVendorDocument: () => ({ mutate: noop, isPending: false }),
  useVendorDocumentDownload: () => useVendorDocumentDownloadMock(),
}));
// Heavy child components — we don't exercise their internals here.
vi.mock('@/features/vendors/components/VendorForm', () => ({
  VendorForm: () => null,
}));
vi.mock('@/features/vendors/components/VendorDocumentUpload', () => ({
  VendorDocumentUpload: () => null,
}));
vi.mock('@/features/vendors/components/TradeMultiSelect', () => ({
  TradeMultiSelect: () => null,
}));

import { VendorDetailPage } from '../VendorDetailPage';

const baseVendor = {
  id: 'v-1',
  company_name: 'Acme Co',
  address: null,
  city: null,
  state: null,
  zip_code: null,
  insurance_expiration_date: null,
  insurance_coverage_amount: null,
  bonding_capacity: null,
  max_active_jobs: null,
  current_active_jobs: 0,
  notes: null,
  status: 'active',
  onboarding_status: 'pending',
  vendor_contacts: [],
  vendor_trades: [],
  vendor_documents: [],
  vendor_flags: [],
};

function renderPage() {
  return renderWithRouter(
    <Routes>
      <Route path="/vendors/:id" element={<VendorDetailPage />} />
    </Routes>,
    { initialEntries: ['/vendors/v-1'] },
  );
}

describe('VendorDetailPage — Communication tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useVendorMock.mockReturnValue({
      data: baseVendor,
      isLoading: false,
      error: null,
    });
  });

  it('renders the Communication tab with the email-log count in the label', () => {
    useVendorEmailLogMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'e1',
            recipient_email: 'a@b.com',
            email_type: 'bid_invitation',
            subject: 's1',
            status: 'sent',
            sent_at: '2026-05-30T10:00:00Z',
            error_message: null,
          },
          {
            id: 'e2',
            recipient_email: 'a@b.com',
            email_type: 'bid_reminder',
            subject: 's2',
            status: 'sent',
            sent_at: '2026-05-30T11:00:00Z',
            error_message: null,
          },
        ],
      },
      isLoading: false,
    });

    renderPage();

    expect(screen.getByRole('tab', { name: /Communication\s*2/ })).toBeInTheDocument();
  });

  it('does not fetch the email log until the Communication tab is active', () => {
    useVendorEmailLogMock.mockReturnValue({ data: undefined, isLoading: false });

    renderPage();

    // First mount: tab is "overview" so the hook receives enabled=false.
    expect(useVendorEmailLogMock).toHaveBeenCalledWith('v-1', false);
    expect(
      useVendorEmailLogMock.mock.calls.every(([, enabled]) => enabled === false),
    ).toBe(true);
  });

  it('renders EmailLogTable rows when the Communication tab is activated', () => {
    useVendorEmailLogMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'e1',
            recipient_email: 'vendor@example.com',
            email_type: 'bid_invitation',
            subject: 'Bid Invitation: Rough Grading',
            status: 'sent',
            sent_at: '2026-05-30T10:00:00Z',
            error_message: null,
          },
        ],
      },
      isLoading: false,
    });

    renderPage();

    fireEvent.click(screen.getByRole('tab', { name: /Communication/ }));

    // The shared Table renders both desktop and mobile views, so each row
    // value can appear more than once in the DOM.
    expect(screen.getAllByText('vendor@example.com').length).toBeGreaterThan(0);
    expect(
      screen.getAllByText('Bid Invitation: Rough Grading').length,
    ).toBeGreaterThan(0);
  });
});
