/**
 * The contract section's visibility matrix.
 *
 * The section resolves award -> contract -> envelope, in that order. Keying it off
 * the contract row (as it did) hides the worst state there is: the envelope send
 * can fail BEFORE the contract row is written, leaving an award that looks fine
 * and no panel at all, with nothing telling the PM the vendor got nothing.
 *
 * The envelope row is the discriminator. Award status alone is not: a healthy
 * in-flight contract and a failed send both sit at `pending_acceptance`. And
 * `contracts.status` is not either — `sent_for_signature` is written inside the
 * send, before the part that can fail.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { TaskDetailPage } from '../TaskDetailPage';
import type { TaskAwardState } from '@/features/milestones/api/milestone.queries';

const PROJECT_ID = 'p1';
const TASK_ID = 't1';

const useTaskContractStateMock = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useParams: () => ({ id: PROJECT_ID, taskId: TASK_ID }) };
});

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock('@/features/tasks/hooks/useTask', () => ({
  useTask: () => ({
    data: {
      id: TASK_ID,
      project_id: PROJECT_ID,
      trade_id: 'trade-dev',
      name: 'Mass Grading',
      description: null,
      phase: 'development',
      bid_type: 'competitive',
      budget_estimate: 5000,
      sort_order: 1,
      status: 'awarded',
      trade_name: 'Grading',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      deleted_at: null,
    },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    isFetching: false,
  }),
}));
vi.mock('@/features/projects/hooks/useProject', () => ({
  useProject: () => ({ data: { archived_at: null } }),
}));
vi.mock('@/features/tasks/hooks/useUpdateTask', () => ({
  useUpdateTask: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/features/tasks/hooks/useDeleteTask', () => ({
  useDeleteTask: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/features/bids/hooks/useBidPackagesForTask', () => ({
  useBidPackagesForTask: () => ({ data: [], isLoading: false }),
}));
vi.mock('@/features/milestones/hooks/useTaskContractState', () => ({
  useTaskContractState: () => useTaskContractStateMock(),
}));
vi.mock('@/features/tasks/components/TaskForm', () => ({ TaskForm: () => null }));
vi.mock('@/features/contracts/components/ContractPanel', () => ({
  ContractPanel: () => <div>CONTRACT_PANEL</div>,
}));
vi.mock('@/features/milestones/components/MilestonesCard', () => ({
  MilestonesCard: () => <div>MILESTONES_CARD</div>,
}));

function state(over: Partial<TaskAwardState> = {}): TaskAwardState {
  return {
    awardId: 'award-1',
    awardStatus: 'pending_acceptance',
    vendorCompanyName: 'Acme Grading LLC',
    contract: {
      id: 'c-1',
      status: 'sent_for_signature',
      contract_number: 'CON-2026-ABCD1234',
      start_date: null,
      end_date: null,
    },
    hasEnvelope: true,
    ...over,
  };
}

const alertShown = () => screen.queryByText(/contract was not delivered/i) !== null;

beforeEach(() => vi.clearAllMocks());

describe('TaskDetailPage contract section', () => {
  it('renders nothing contract-related when there is no active award', () => {
    useTaskContractStateMock.mockReturnValue({ data: null });
    renderWithRouter(<TaskDetailPage />);

    expect(alertShown()).toBe(false);
    expect(screen.queryByText('CONTRACT_PANEL')).not.toBeInTheDocument();
    expect(screen.queryByText('MILESTONES_CARD')).not.toBeInTheDocument();
  });

  it('shows the Contract card and no Alert once the envelope exists', () => {
    useTaskContractStateMock.mockReturnValue({ data: state() });
    renderWithRouter(<TaskDetailPage />);

    expect(screen.getByText('CONTRACT_PANEL')).toBeInTheDocument();
    expect(screen.getByText('MILESTONES_CARD')).toBeInTheDocument();
    expect(alertShown()).toBe(false);
  });

  it('shows the Alert when the award is pending and no envelope went out', () => {
    useTaskContractStateMock.mockReturnValue({ data: state({ hasEnvelope: false }) });
    renderWithRouter(<TaskDetailPage />);

    expect(alertShown()).toBe(true);
    expect(screen.getByRole('button', { name: 'Send contract' })).toBeInTheDocument();
  });

  it('shows the Alert even when the send died before the contract row was written', () => {
    // The case that rendered completely blank under the contract-keyed read.
    useTaskContractStateMock.mockReturnValue({
      data: state({ hasEnvelope: false, contract: null }),
    });
    renderWithRouter(<TaskDetailPage />);

    expect(alertShown()).toBe(true);
    expect(screen.queryByText('CONTRACT_PANEL')).not.toBeInTheDocument();
  });

  it('never offers to send on an accepted award', () => {
    useTaskContractStateMock.mockReturnValue({
      data: state({ awardStatus: 'accepted', hasEnvelope: false }),
    });
    renderWithRouter(<TaskDetailPage />);

    expect(alertShown()).toBe(false);
  });

  it.each(['declined_by_vendor', 'cancelled'])(
    'never offers to send on a %s award',
    (awardStatus) => {
      // fetchTaskAwardState already filters these out, so in practice the page
      // sees no award at all. Asserted here anyway: the component must refuse on
      // its own, so that widening the query later cannot start offering to push a
      // contract for an award the vendor already rejected.
      useTaskContractStateMock.mockReturnValue({
        data: state({ awardStatus, hasEnvelope: false }),
      });
      renderWithRouter(<TaskDetailPage />);

      expect(alertShown()).toBe(false);
    },
  );

  it('hides rather than disables the action in the happy path', () => {
    useTaskContractStateMock.mockReturnValue({ data: state() });
    renderWithRouter(<TaskDetailPage />);

    // Not present at all — a greyed-out button here is clutter that invites
    // clicking.
    expect(screen.queryByRole('button', { name: 'Send contract' })).not.toBeInTheDocument();
  });
});
