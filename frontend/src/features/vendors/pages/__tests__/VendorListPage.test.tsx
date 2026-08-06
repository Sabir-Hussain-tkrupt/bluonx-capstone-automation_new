import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';

// delay: null removes the wait between keystrokes. With the default, typing a
// company name plus a full contact took long enough to trip the 5s timeout
// when the whole suite runs in parallel, making this file intermittently fail.
const userEvent = userEventBase.setup({ delay: null });
import { renderWithRouter } from '@/test/test-utils';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});
import { VendorListPage } from '../VendorListPage';
import { makeApiError } from '@/test/api-error';

const useVendorsMock = vi.fn();
const createMutateMock = vi.fn();

vi.mock('@/features/vendors/hooks/useVendors', () => ({
  useVendors: () => useVendorsMock(),
}));

vi.mock('@/features/vendors/hooks/useTrades', () => ({
  useTrades: () => ({ data: [] }),
}));

vi.mock('@/features/vendors/hooks/useCreateVendor', () => ({
  useCreateVendor: () => ({ mutate: createMutateMock, isPending: false }),
}));

vi.mock('@/features/vendors/hooks/useInsuranceExpiringCount', () => ({
  useInsuranceExpiringCount: () => ({ data: { count: 0 }, isLoading: false, isError: false }),
}));

const emptySuccess = {
  data: { items: [], total: 0, page: 1, page_size: 25 },
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
  isFetching: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  useVendorsMock.mockReturnValue(emptySuccess);
});

describe('VendorListPage load failures', () => {
  it('reports a failed fetch instead of claiming there are no vendors', () => {
    // The regression: isError was dropped, so a dead API, an expired session
    // and a permission denial all rendered "No vendors found — try adjusting
    // your filters", telling the user to fix a filter that was never the
    // problem.
    useVendorsMock.mockReturnValue({
      ...emptySuccess,
      data: undefined,
      isError: true,
      error: makeApiError('Unable to reach the server. Check your connection.', 0, 'NETWORK_ERROR'),
    });

    renderWithRouter(<VendorListPage />);

    expect(screen.getByText('Could not load vendors')).toBeInTheDocument();
    expect(
      screen.getByText('Unable to reach the server. Check your connection.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('No vendors found')).not.toBeInTheDocument();
    expect(screen.queryByText('Try adjusting your filters.')).not.toBeInTheDocument();
  });

  it('offers a retry that refetches', async () => {
    const refetch = vi.fn();
    useVendorsMock.mockReturnValue({
      ...emptySuccess,
      data: undefined,
      isError: true,
      error: makeApiError('Server error', 500, 'SERVER_ERROR'),
      refetch,
    });

    renderWithRouter(<VendorListPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(refetch).toHaveBeenCalled();
  });

  it('still shows the ordinary empty state when the fetch succeeded with no rows', () => {
    renderWithRouter(<VendorListPage />);

    expect(screen.getByText('No vendors found')).toBeInTheDocument();
    expect(screen.queryByText('Could not load vendors')).not.toBeInTheDocument();
  });
});

describe('VendorListPage create form', () => {
  async function openFormAndFillIn(companyName: string) {
    await userEvent.click(screen.getByRole('button', { name: '+ Add Vendor' }));

    const dialog = screen.getByRole('dialog');
    const companyInput = dialog.querySelector<HTMLInputElement>('input[name="company_name"]')!;
    await userEvent.type(companyInput, companyName);

    await userEvent.type(within(dialog).getByPlaceholderText('Contact name *'), 'Dana Reed');
    await userEvent.type(within(dialog).getByPlaceholderText('Email *'), 'dana@example.com');
    await userEvent.click(within(dialog).getByRole('button', { name: '+ Add Contact' }));

    return dialog;
  }

  it('opens empty again after a successful create', async () => {
    // The regression: the form was mounted permanently and the success path
    // closed it by flipping the parent's flag rather than calling the form's
    // own reset, so the next "Add Vendor" opened pre-filled with the vendor
    // that had just been created — one submit away from a near-duplicate.
    createMutateMock.mockImplementation((_input, opts) => opts.onSuccess?.());

    renderWithRouter(<VendorListPage />);
    await openFormAndFillIn('Acme Paving');
    await userEvent.click(screen.getByRole('button', { name: 'Create Vendor' }));

    expect(createMutateMock).toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '+ Add Vendor' }));

    const reopened = screen.getByRole('dialog');
    expect(
      reopened.querySelector<HTMLInputElement>('input[name="company_name"]')!.value,
    ).toBe('');
    expect(within(reopened).queryByText('Acme Paving')).not.toBeInTheDocument();
    expect(within(reopened).queryByText('Dana Reed')).not.toBeInTheDocument();
  });

  it('does not carry an in-progress contact draft across a cancel', async () => {
    renderWithRouter(<VendorListPage />);

    await userEvent.click(screen.getByRole('button', { name: '+ Add Vendor' }));
    const dialog = screen.getByRole('dialog');
    // Typed but never added — this draft used to survive the close.
    await userEvent.type(within(dialog).getByPlaceholderText('Contact name *'), 'Half Typed');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }));

    await userEvent.click(screen.getByRole('button', { name: '+ Add Vendor' }));

    const reopened = screen.getByRole('dialog');
    expect(
      within(reopened).getByPlaceholderText<HTMLInputElement>('Contact name *').value,
    ).toBe('');
  });

  it('rejects a malformed contact email before submitting', async () => {
    renderWithRouter(<VendorListPage />);

    await userEvent.click(screen.getByRole('button', { name: '+ Add Vendor' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByPlaceholderText('Contact name *'), 'Dana Reed');
    await userEvent.type(within(dialog).getByPlaceholderText('Email *'), 'not-an-email');
    await userEvent.click(within(dialog).getByRole('button', { name: '+ Add Contact' }));

    expect(
      within(dialog).getByText('Enter a valid email address for the contact.'),
    ).toBeInTheDocument();
    expect(within(dialog).queryByText('Dana Reed')).not.toBeInTheDocument();
  });
});

describe('VendorListPage create redirect', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useVendorsMock.mockReturnValue(emptySuccess);
  });

  it('lands on the new vendor detail page after a successful create', async () => {
    renderWithRouter(<VendorListPage />);

    await userEvent.click(screen.getByRole('button', { name: '+ Add Vendor' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getAllByRole('textbox')[0], 'Acme Grading');
    await userEvent.type(within(dialog).getByPlaceholderText('Contact name *'), 'Dana Reed');
    await userEvent.type(within(dialog).getByPlaceholderText('Email *'), 'dana@acme.com');
    await userEvent.click(within(dialog).getByRole('button', { name: '+ Add Contact' }));
    await userEvent.click(within(dialog).getByRole('button', { name: /create vendor/i }));

    expect(createMutateMock).toHaveBeenCalledTimes(1);

    // Drive onSuccess the way React Query would. A new vendor cannot be marked
    // onboarding-complete at creation, so the detail page (where the insurance
    // upload lives) is the next step and we should land there.
    const onSuccess = createMutateMock.mock.calls[0][1].onSuccess;
    onSuccess({ id: 'v-new-1', company_name: 'Acme Grading' });

    expect(navigateMock).toHaveBeenCalledWith('/vendors/v-new-1');
  });

  it('does not navigate when the create fails', async () => {
    renderWithRouter(<VendorListPage />);

    await userEvent.click(screen.getByRole('button', { name: '+ Add Vendor' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getAllByRole('textbox')[0], 'Acme Grading');
    await userEvent.type(within(dialog).getByPlaceholderText('Contact name *'), 'Dana Reed');
    await userEvent.type(within(dialog).getByPlaceholderText('Email *'), 'dana@acme.com');
    await userEvent.click(within(dialog).getByRole('button', { name: '+ Add Contact' }));
    await userEvent.click(within(dialog).getByRole('button', { name: /create vendor/i }));

    const onError = createMutateMock.mock.calls[0][1].onError;
    onError(makeApiError('A vendor named that already exists.', 409, 'CONFLICT'));

    expect(navigateMock).not.toHaveBeenCalled();
  });
});
