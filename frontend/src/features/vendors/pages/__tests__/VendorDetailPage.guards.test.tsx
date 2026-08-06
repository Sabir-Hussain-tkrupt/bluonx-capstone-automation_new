import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { VendorDetailPage } from '../VendorDetailPage';
import { makeApiError } from '@/test/api-error';

const userEvent = userEventBase.setup({ delay: null });

const VENDOR_ID = 'de305d54-75b4-431b-adb2-eb6b9e546014';

const useVendorMock = vi.fn();
const deleteVendorMutate = vi.fn();
const deleteContactMutate = vi.fn();
const removeTradeMutate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useParams: () => ({ id: VENDOR_ID }) };
});

vi.mock('@/features/vendors/hooks/useVendor', () => ({
  useVendor: () => useVendorMock(),
}));

vi.mock('@/features/vendors/hooks/useUpdateVendor', () => ({
  useUpdateVendor: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/features/vendors/hooks/useDeleteVendor', () => ({
  useDeleteVendor: () => ({ mutate: deleteVendorMutate, isPending: false }),
}));

vi.mock('@/features/vendors/hooks/useVendorContacts', () => ({
  useCreateContact: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateContact: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteContact: () => ({ mutate: deleteContactMutate, isPending: false }),
}));

vi.mock('@/features/vendors/hooks/useVendorTrades', () => ({
  useAddVendorTrades: () => ({ mutate: vi.fn(), isPending: false }),
  useRemoveVendorTrade: () => ({ mutate: removeTradeMutate, isPending: false }),
}));

vi.mock('@/features/vendors/hooks/useVendorDocuments', () => ({
  useDeleteVendorDocument: () => ({ mutate: vi.fn(), isPending: false }),
  useVendorDocumentDownload: () => ({ download: vi.fn(), downloadingId: null }),
  useUploadVendorDocument: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/features/vendors/hooks/useVendorEmailLog', () => ({
  useVendorEmailLog: () => ({ data: undefined, isLoading: false }),
}));

vi.mock('@/features/vendors/hooks/useTrades', () => ({
  useTrades: () => ({ data: [], isLoading: false }),
}));

function contact(overrides: Record<string, unknown> = {}) {
  return {
    id: 'c1',
    vendor_id: VENDOR_ID,
    full_name: 'Dana Reed',
    email: 'dana@example.com',
    phone: null,
    title: null,
    is_primary: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function vendorWith(overrides: Record<string, unknown> = {}) {
  return {
    id: VENDOR_ID,
    company_name: 'Acme Grading LLC',
    address: null,
    city: null,
    state: null,
    zip_code: null,
    latitude: null,
    longitude: null,
    insurance_expiration_date: null,
    insurance_coverage_amount: null,
    bonding_capacity: null,
    max_active_jobs: null,
    current_active_jobs: 0,
    onboarding_status: 'complete',
    status: 'active',
    notes: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    deleted_at: null,
    vendor_contacts: [contact()],
    vendor_trades: [],
    vendor_documents: [],
    vendor_flags: [],
    ...overrides,
  };
}

function loaded(vendor: Record<string, unknown>) {
  return {
    data: vendor,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    isFetching: false,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  useVendorMock.mockReturnValue(loaded(vendorWith()));
});

describe('VendorDetailPage load failures', () => {
  it('says the vendor is missing on a 404', () => {
    useVendorMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: makeApiError('The requested resource was not found.', 404, 'NOT_FOUND'),
      refetch: vi.fn(),
      isFetching: false,
    });

    renderWithRouter(<VendorDetailPage />);

    expect(screen.getByText('Vendor not found')).toBeInTheDocument();
  });

  it('reports a network failure as a load error, not a deleted vendor', () => {
    // The regression: any error rendered "does not exist or has been deleted",
    // sending the user to look for a vendor that is actually fine.
    useVendorMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: makeApiError('Unable to reach the server. Check your connection.', 0, 'NETWORK_ERROR'),
      refetch: vi.fn(),
      isFetching: false,
    });

    renderWithRouter(<VendorDetailPage />);

    expect(screen.getByText('Could not load vendor')).toBeInTheDocument();
    expect(
      screen.getByText('Unable to reach the server. Check your connection.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Vendor not found')).not.toBeInTheDocument();
  });

  it('offers a retry on a load failure', async () => {
    const refetch = vi.fn();
    useVendorMock.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: makeApiError('A server error occurred.', 500, 'SERVER_ERROR'),
      refetch,
      isFetching: false,
    });

    renderWithRouter(<VendorDetailPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(refetch).toHaveBeenCalled();
  });
});

describe('VendorDetailPage destructive actions', () => {
  it('confirms before deleting the vendor and surfaces the guard message', async () => {
    renderWithRouter(<VendorDetailPage />);

    await userEvent.click(screen.getByRole('button', { name: 'More actions' }));
    await userEvent.click(screen.getByText('Delete'));

    // Nothing fired yet — the dialog is the gate.
    expect(deleteVendorMutate).not.toHaveBeenCalled();
    expect(screen.getByText('Delete Vendor', { selector: 'h2, h3' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Delete Vendor' }));
    expect(deleteVendorMutate).toHaveBeenCalled();
  });

  it('confirms before removing a trade', async () => {
    useVendorMock.mockReturnValue(
      loaded(
        vendorWith({
          vendor_trades: [
            {
              id: 'vt1',
              vendor_id: VENDOR_ID,
              trade_id: 't1',
              trades: { name: 'Paving', phase: 'development' },
              created_at: '2026-01-01T00:00:00Z',
            },
          ],
        }),
      ),
    );

    renderWithRouter(<VendorDetailPage />);
    await userEvent.click(screen.getByRole('tab', { name: /Trades/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Remove Paving' }));

    // The regression: this used to delete on the first click.
    expect(removeTradeMutate).not.toHaveBeenCalled();
    expect(screen.getByText('Remove Trade', { selector: 'h2, h3' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Remove Trade' }));
    expect(removeTradeMutate).toHaveBeenCalled();
  });
});

describe('VendorDetailPage last-contact guard', () => {
  it('disables Delete when only one contact remains', async () => {
    renderWithRouter(<VendorDetailPage />);
    await userEvent.click(screen.getByRole('tab', { name: /Contacts/ }));

    expect(screen.getByRole('button', { name: 'Delete' })).toBeDisabled();
  });

  it('allows deleting once a second contact exists, behind a confirmation', async () => {
    useVendorMock.mockReturnValue(
      loaded(
        vendorWith({
          vendor_contacts: [
            contact(),
            contact({ id: 'c2', full_name: 'Sam Lee', email: 'sam@example.com', is_primary: false }),
          ],
        }),
      ),
    );

    renderWithRouter(<VendorDetailPage />);
    await userEvent.click(screen.getByRole('tab', { name: /Contacts/ }));

    const deleteButtons = screen.getAllByRole('button', { name: 'Delete' });
    expect(deleteButtons[0]).toBeEnabled();

    await userEvent.click(deleteButtons[1]);
    expect(deleteContactMutate).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'Delete Contact' }));
    expect(deleteContactMutate).toHaveBeenCalledWith(
      expect.objectContaining({ contactId: 'c2' }),
      expect.anything(),
    );
  });
});

describe('VendorDetailPage overview values', () => {
  it('shows a zero coverage amount instead of treating it as unset', () => {
    useVendorMock.mockReturnValue(
      loaded(vendorWith({ insurance_coverage_amount: 0, max_active_jobs: 0 })),
    );

    renderWithRouter(<VendorDetailPage />);

    expect(screen.getByText('$0')).toBeInTheDocument();
    expect(screen.getByText('0 / 0')).toBeInTheDocument();
  });
});
