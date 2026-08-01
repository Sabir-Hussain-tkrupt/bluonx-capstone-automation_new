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
  EMAIL_LOG_PAGE_SIZE: 25,
  useVendorEmailLog: (id: string, enabled: boolean, page: number) =>
    useVendorEmailLogMock(id, enabled, page),
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

function renderPage(search?: string) {
  return renderWithRouter(
    <Routes>
      <Route path="/vendors/:id" element={<VendorDetailPage />} />
    </Routes>,
    { initialEntries: [{ pathname: '/vendors/v-1', search }] },
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

  it('shows the server-side total in the tab label, not the page length', () => {
    // The badge must read `total`. Reading items.length would just report the
    // page size once a vendor has more emails than fit on one page.
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
        total: 87,
        page: 1,
        page_size: 25,
      },
      isLoading: false,
    });

    renderPage();

    expect(screen.getByRole('tab', { name: /Communication\s*87/ })).toBeInTheDocument();
  });

  it('does not fetch the email log until the Communication tab is active', () => {
    useVendorEmailLogMock.mockReturnValue({ data: undefined, isLoading: false });

    renderPage();

    // First mount: tab is "overview" so the hook receives enabled=false.
    expect(useVendorEmailLogMock).toHaveBeenCalledWith('v-1', false, 1);
    expect(
      useVendorEmailLogMock.mock.calls.every(([, enabled]) => enabled === false),
    ).toBe(true);
  });

  it('fetches the email log on a deep link to the Communication tab', () => {
    useVendorEmailLogMock.mockReturnValue({ data: undefined, isLoading: true });

    renderPage('?tab=communication');

    // The tab lives in the URL now, so a shared link can land here directly and
    // the gated fetch fires on first paint rather than waiting for a click.
    expect(useVendorEmailLogMock).toHaveBeenCalledWith('v-1', true, 1);
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
        total: 1,
        page: 1,
        page_size: 25,
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

  it('pages the log server-side rather than fetching every row', () => {
    // The whole point of the change: a vendor with thousands of emails must
    // never have them all pulled into one response.
    useVendorEmailLogMock.mockReturnValue({
      data: {
        items: [
          {
            id: 'e1',
            recipient_email: 'vendor@example.com',
            email_type: 'bid_invitation',
            subject: 'page one',
            status: 'sent',
            sent_at: '2026-05-30T10:00:00Z',
            error_message: null,
          },
        ],
        total: 60,
        page: 1,
        page_size: 25,
      },
      isLoading: false,
    });

    renderPage('?tab=communication');

    // One row rendered, but the footer knows there are 60 across 3 pages.
    expect(screen.getByLabelText('Pagination')).toBeInTheDocument();
    expect(screen.getByText('1 / 3')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));

    expect(useVendorEmailLogMock).toHaveBeenLastCalledWith('v-1', true, 2);
  });
});
