/**
 * Form validation on BidTemplateFormPage.
 *
 * The headline case is the Lump Sum toggle: item rules used to run
 * unconditionally while the items section only renders for structured
 * templates, so a half-filled item left behind by a toggle failed validation
 * with the error painted inside a hidden section and Save silently did
 * nothing. Also covers the trim rules that mirror the backend.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { BidTemplateFormPage } from '../BidTemplateFormPage';

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return {
    ...actual,
    useParams: () => ({}), // create mode
    useNavigate: () => vi.fn(),
  };
});

const useBidTemplateMock = vi.fn(() => ({
  data: undefined,
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
  isFetching: false,
}));
vi.mock('@/features/bid-templates/hooks/useBidTemplate', () => ({
  useBidTemplate: () => useBidTemplateMock(),
}));

vi.mock('@/features/vendors/hooks/useTrades', () => ({
  useTrades: () => ({ data: [] }),
}));

const createMutationMock = { mutate: vi.fn(), isPending: false };
const updateMutationMock = { mutate: vi.fn(), isPending: false };
const duplicateMutationMock = { mutate: vi.fn(), isPending: false };

vi.mock('@/features/bid-templates/hooks/useCreateBidTemplate', () => ({
  useCreateBidTemplate: () => createMutationMock,
}));
vi.mock('@/features/bid-templates/hooks/useUpdateBidTemplate', () => ({
  useUpdateBidTemplate: () => updateMutationMock,
}));
vi.mock('@/features/bid-templates/hooks/useDuplicateBidTemplate', () => ({
  useDuplicateBidTemplate: () => duplicateMutationMock,
}));

/** The Bid Format toggle: checked = Lump Sum, unchecked = Line Items. */
function bidFormatToggle() {
  return screen.getByRole('checkbox');
}

function submit() {
  return screen.getByRole('button', { name: /create template/i });
}

describe('BidTemplateFormPage validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('submits after toggling to Lump Sum with a half-filled line item', async () => {
    const user = userEvent.setup();
    renderWithRouter(<BidTemplateFormPage />);

    await user.type(screen.getByPlaceholderText(/Grading & Earthwork/i), 'My Template');

    // Switch to Line Items, add an item, leave its description blank.
    await user.click(bidFormatToggle());
    await user.click(screen.getByRole('button', { name: /add item/i }));

    // Switch back to Lump Sum. The blank item is now unreachable in the UI.
    await user.click(bidFormatToggle());

    await user.click(submit());

    // Pre-fix this never fired: zod failed on the hidden item's description.
    await waitFor(() => {
      expect(createMutationMock.mutate).toHaveBeenCalledTimes(1);
    });
    expect(createMutationMock.mutate.mock.calls[0][0]).toMatchObject({
      name: 'My Template',
      is_lump_sum: true,
      items: [],
    });
  });

  it('rejects a whitespace-only template name', async () => {
    const user = userEvent.setup();
    renderWithRouter(<BidTemplateFormPage />);

    await user.type(screen.getByPlaceholderText(/Grading & Earthwork/i), '   ');
    await user.click(submit());

    expect(await screen.findByText(/Template name is required/i)).toBeInTheDocument();
    expect(createMutationMock.mutate).not.toHaveBeenCalled();
  });

  it('trims the name before sending it', async () => {
    const user = userEvent.setup();
    renderWithRouter(<BidTemplateFormPage />);

    await user.type(screen.getByPlaceholderText(/Grading & Earthwork/i), '  Padded  ');
    await user.click(submit());

    await waitFor(() => expect(createMutationMock.mutate).toHaveBeenCalled());
    expect(createMutationMock.mutate.mock.calls[0][0].name).toBe('Padded');
  });

  it('rejects a whitespace-only item description on a structured template', async () => {
    const user = userEvent.setup();
    renderWithRouter(<BidTemplateFormPage />);

    await user.type(screen.getByPlaceholderText(/Grading & Earthwork/i), 'Structured');
    await user.click(bidFormatToggle());
    await user.click(screen.getByRole('button', { name: /add item/i }));

    await user.type(screen.getByPlaceholderText(/Mobilization, Grading per acre/i), '   ');
    await user.type(screen.getByPlaceholderText(/LF, SY, EA/i), 'CY');

    await user.click(submit());

    expect(await screen.findByText(/Description is required/i)).toBeInTheDocument();
    expect(createMutationMock.mutate).not.toHaveBeenCalled();
  });

  it('rejects a whitespace-only unit of measure on a unit-price item', async () => {
    const user = userEvent.setup();
    renderWithRouter(<BidTemplateFormPage />);

    await user.type(screen.getByPlaceholderText(/Grading & Earthwork/i), 'Structured');
    await user.click(bidFormatToggle());
    await user.click(screen.getByRole('button', { name: /add item/i }));

    await user.type(
      screen.getByPlaceholderText(/Mobilization, Grading per acre/i),
      'Excavation',
    );
    await user.type(screen.getByPlaceholderText(/LF, SY, EA/i), '   ');

    await user.click(submit());

    expect(
      await screen.findByText(/Unit of measure is required/i),
    ).toBeInTheDocument();
    expect(createMutationMock.mutate).not.toHaveBeenCalled();
  });

  it('still requires at least one item on a structured template', async () => {
    const user = userEvent.setup();
    renderWithRouter(<BidTemplateFormPage />);

    await user.type(screen.getByPlaceholderText(/Grading & Earthwork/i), 'Structured');
    await user.click(bidFormatToggle());

    await user.click(submit());

    expect(
      await screen.findByText(/At least one line item is required/i),
    ).toBeInTheDocument();
    expect(createMutationMock.mutate).not.toHaveBeenCalled();
  });
});
