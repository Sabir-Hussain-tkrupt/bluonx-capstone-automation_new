/**
 * The moment-of-failure catch on the comparison page.
 *
 * POST /awards awaits the envelope send before responding, so the backend already
 * knows the vendor got nothing while the PM is still standing on this page. A
 * clean success toast there is worse than no feedback at all: it is the difference
 * between the vendor waiting minutes and the vendor waiting days.
 *
 * This page is the catch, not the home. The durable surface is the task detail
 * page, which reads the state back from the database.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { BidPackageComparePage } from '../BidPackageComparePage';

const PROJECT_ID = 'p1';
const TASK_ID = 't1';
const PACKAGE_ID = 'bp1';
const VENDOR = 'Acme Grading LLC';

const awardMutate = vi.fn();
const toastMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useParams: () => ({ id: PROJECT_ID, taskId: TASK_ID, bidPackageId: PACKAGE_ID }),
  };
});

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock('@/components/ui/Toast/useToast', () => ({ useToast: () => ({ toast: toastMock }) }));

vi.mock('@/features/bids/hooks/useBidPackageDetail', () => ({
  useBidPackageDetail: () => ({
    data: {
      id: PACKAGE_ID,
      task_name: 'Mass Grading',
      round_number: 1,
      status: 'closed',
      invitation_summary: { submitted: 2, total: 2 },
      award: null,
    },
    isLoading: false,
    error: null,
  }),
}));
vi.mock('@/features/tasks/hooks/useTask', () => ({
  useTask: () => ({ data: { bid_type: 'competitive' } }),
}));
vi.mock('@/features/projects/hooks/useProject', () => ({ useProject: () => ({ data: null }) }));
vi.mock('@/features/bids/hooks/useBidPackageScores', () => ({
  useBidPackageScores: () => ({
    data: {
      // One score so the page takes the table branch (which owns onAward) rather
      // than the empty-cohort CTA.
      scores: [
        {
          bid_submission_id: 'sub-1',
          vendor_company_name: VENDOR,
          scoring_metadata: { inputs: { this_total: 145000 } },
          scored_at: '2026-08-01T00:00:00Z',
        },
      ],
      recommendation: null,
      cohort_size: 1,
      valid_submission_count: 1,
      latest_submission_at: '2026-08-01T00:00:00Z',
    },
    isLoading: false,
    error: null,
  }),
}));
vi.mock('@/features/bids/hooks/useComputeBidPackageScores', () => ({
  useComputeBidPackageScores: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/features/bids/hooks/useCreateAward', () => ({
  useCreateAward: () => ({ mutate: awardMutate, isPending: false }),
}));

// Heavy children stubbed to the one interaction this test needs: the table's
// Award action, and the dialog's confirm.
vi.mock('@/features/bids/components/ComparisonTable', () => ({
  ComparisonTable: ({
    onAward,
  }: {
    onAward: (bidSubmissionId: string, vendorName: string) => void;
  }) => <button onClick={() => onAward('sub-1', VENDOR)}>START_AWARD</button>,
}));
vi.mock('@/features/bids/components/AwardDialog', () => ({
  AwardDialog: ({
    isOpen,
    onConfirm,
  }: {
    isOpen: boolean;
    onConfirm: (args: Record<string, unknown>) => void;
  }) =>
    isOpen ? (
      <button onClick={() => onConfirm({ has_override: false, signer_id: 's-1' })}>
        CONFIRM_AWARD
      </button>
    ) : null,
}));
vi.mock('@/features/bids/components/BidAmountBarChart', () => ({
  BidAmountBarChart: () => null,
}));
vi.mock('@/features/bids/components/BidSubmissionDetailModal', () => ({
  BidSubmissionDetailModal: () => null,
}));

function award(over: Record<string, unknown> = {}) {
  return { id: 'award-1', status: 'pending_acceptance', envelope_sent: true, ...over };
}

/** Award a vendor and resolve the mutation with `result`. */
async function awardWith(
  ue: ReturnType<typeof userEvent.setup>,
  result: Record<string, unknown>,
) {
  awardMutate.mockImplementation((_payload, opts) => opts.onSuccess(result));
  await ue.click(screen.getByText('START_AWARD'));
  await ue.click(await screen.findByText('CONFIRM_AWARD'));
}

const alertShown = () => screen.queryByText(/contract was not delivered/i) !== null;

beforeEach(() => vi.clearAllMocks());

describe('BidPackageComparePage award send failure', () => {
  it('replaces the success toast with the failure Alert when the send failed', async () => {
    const ue = userEvent.setup();
    renderWithRouter(<BidPackageComparePage />);

    await awardWith(ue, award({ envelope_sent: false }));

    await waitFor(() => expect(alertShown()).toBe(true));
    expect(screen.getByRole('alert')).toHaveTextContent(new RegExp(VENDOR, 'i'));
    // The whole point: no clean success feedback for a broken award.
    expect(toastMock).not.toHaveBeenCalled();
  });

  it('offers the same Send contract action as the task detail surface', async () => {
    const ue = userEvent.setup();
    renderWithRouter(<BidPackageComparePage />);

    await awardWith(ue, award({ envelope_sent: false }));

    expect(
      await screen.findByRole('button', { name: 'Send contract' }),
    ).toBeInTheDocument();
    // Never "Resend": nothing was ever sent.
    expect(screen.queryByRole('button', { name: /resend/i })).not.toBeInTheDocument();
  });

  it('toasts success and shows no Alert when the envelope did go out', async () => {
    const ue = userEvent.setup();
    renderWithRouter(<BidPackageComparePage />);

    await awardWith(ue, award({ envelope_sent: true }));

    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ variant: 'success' }),
      ),
    );
    expect(alertShown()).toBe(false);
  });

  it('clears the Alert once the contract has been sent from here', async () => {
    const ue = userEvent.setup();
    const { api } = await import('@/lib/api');
    vi.mocked(api.post).mockResolvedValue({
      data: { envelope_id: 'env-1', status: 'sent', contract_id: 'c-1' },
    } as never);

    renderWithRouter(<BidPackageComparePage />);
    await awardWith(ue, award({ envelope_sent: false }));

    await ue.click(await screen.findByRole('button', { name: 'Send contract' }));
    const dialog = await screen.findByRole('dialog');
    await ue.click(
      (await screen.findAllByRole('button', { name: 'Send contract' })).find((b) =>
        dialog.contains(b),
      )!,
    );

    await waitFor(() => expect(alertShown()).toBe(false));
  });
});
