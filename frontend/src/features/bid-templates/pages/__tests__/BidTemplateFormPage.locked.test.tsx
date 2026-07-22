/**
 * Locked-state UI for BidTemplateFormPage (Task 8.1 freeze guards).
 *
 * When the template detail reports `is_in_use=true`, the form must:
 *  - render a "locked: duplicate to change" banner that names the blocker
 *  - disable the Save Changes button
 *  - expose a Duplicate button that triggers the duplicate mutation
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { BidTemplateFormPage } from '../BidTemplateFormPage';
import type {
  BidTemplateDetail,
} from '@/features/bid-templates/api/bid-template.queries';

// ─── Hook mocks ────────────────────────────────────────────────────────

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return {
    ...actual,
    useParams: () => ({ id: 'tpl-123' }),
    useNavigate: () => vi.fn(),
  };
});

const lockedTemplate: BidTemplateDetail = {
  id: 'tpl-123',
  name: 'Standard Grading Template',
  trade_id: null,
  is_lump_sum: false,
  created_by: 'pm-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  trade_name: 'Grading',
  item_count: 2,
  items: [
    {
      id: 'i-1',
      bid_template_id: 'tpl-123',
      description: 'Mobilization',
      item_type: 'lump_sum',
      unit_of_measure: null,
      sort_order: 0,
    },
    {
      id: 'i-2',
      bid_template_id: 'tpl-123',
      description: 'Excavation',
      item_type: 'unit_price',
      unit_of_measure: 'CY',
      sort_order: 1,
    },
  ],
  is_in_use: true,
  // A live package references it, so it is neither editable nor deletable.
  is_deletable: false,
  referencing_packages: [
    { id: 'pkg-1', task_name: 'Rough Grading', status: 'open' },
  ],
  referencing_packages_total: 1,
};

const editableTemplate: BidTemplateDetail = {
  ...lockedTemplate,
  is_in_use: false,
  is_deletable: true,
  referencing_packages: [],
  referencing_packages_total: 0,
};

const useBidTemplateMock = vi.fn();
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

// ─── Tests ─────────────────────────────────────────────────────────────

describe('BidTemplateFormPage locked state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the locked banner naming the blocking package', () => {
    useBidTemplateMock.mockReturnValue({
      data: lockedTemplate,
      isLoading: false,
      isError: false,
    });

    renderWithRouter(<BidTemplateFormPage />);

    expect(screen.getByText(/In use - locked/i)).toBeInTheDocument();
    // The banner must name the blocking task + its status so the PM knows
    // which round is holding the template.
    expect(screen.getByText(/Rough Grading/)).toBeInTheDocument();
    expect(screen.getByText(/open/)).toBeInTheDocument();
    expect(screen.getByText(/Duplicate to change/i)).toBeInTheDocument();
  });

  it('disables the Save Changes button when locked', () => {
    useBidTemplateMock.mockReturnValue({
      data: lockedTemplate,
      isLoading: false,
      isError: false,
    });

    renderWithRouter(<BidTemplateFormPage />);

    const save = screen.getByRole('button', { name: /save changes/i });
    expect(save).toBeDisabled();
  });

  it('shows a Duplicate button when locked and triggers the duplicate mutation', async () => {
    const user = userEvent.setup();
    useBidTemplateMock.mockReturnValue({
      data: lockedTemplate,
      isLoading: false,
      isError: false,
    });

    renderWithRouter(<BidTemplateFormPage />);

    const dup = screen.getByRole('button', { name: /duplicate/i });
    expect(dup).toBeInTheDocument();

    await user.click(dup);

    expect(duplicateMutationMock.mutate).toHaveBeenCalledTimes(1);
    expect(duplicateMutationMock.mutate.mock.calls[0][0]).toBe('tpl-123');
  });

  it('does not render the locked banner or Duplicate button for editable templates', () => {
    useBidTemplateMock.mockReturnValue({
      data: editableTemplate,
      isLoading: false,
      isError: false,
    });

    renderWithRouter(<BidTemplateFormPage />);

    expect(screen.queryByText(/In use - locked/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /^duplicate$/i }),
    ).not.toBeInTheDocument();

    const save = screen.getByRole('button', { name: /save changes/i });
    expect(save).not.toBeDisabled();
  });
});
