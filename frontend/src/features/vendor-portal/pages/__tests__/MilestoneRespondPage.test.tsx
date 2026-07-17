import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { MilestoneRespondPage } from '../MilestoneRespondPage';
import type { VendorMilestoneContext } from '../../types/portal';
import { PortalApiError } from '../../types/portal';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
}));

const respondMock = vi.fn();
vi.mock('../../services/portalApi', () => ({
  respondToMilestone: (...a: unknown[]) => respondMock(...a),
}));

const ctxHolder = vi.hoisted(() => ({
  current: null as VendorMilestoneContext | null,
}));
vi.mock('../../hooks/useMilestoneContext', () => ({
  useMilestoneContext: () => ctxHolder.current,
}));

function ctx(
  overrides: Partial<VendorMilestoneContext> = {},
): VendorMilestoneContext {
  return {
    milestone_alert_id: 'alert-1',
    milestone_id: 'ms-1',
    milestone_name: 'Rough Grading',
    project_name: 'Phoenix Park',
    task_name: 'Grading',
    vendor_company_name: 'Apex',
    check_type: 'progress',
    end_date: '2026-08-01',
    cycle_number: 1,
    ...overrides,
  };
}

describe('MilestoneRespondPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the start question for a start check', () => {
    ctxHolder.current = ctx({ check_type: 'start' });
    renderWithRouter(<MilestoneRespondPage />);
    expect(screen.getByText('Has this work started?')).toBeInTheDocument();
  });

  it('renders the completion question for a completion check', () => {
    ctxHolder.current = ctx({ check_type: 'completion' });
    renderWithRouter(<MilestoneRespondPage />);
    expect(screen.getByText('Is this work complete?')).toBeInTheDocument();
  });

  it('renders the progress question with the end date', () => {
    ctxHolder.current = ctx({ check_type: 'progress' });
    renderWithRouter(<MilestoneRespondPage />);
    expect(screen.getByText(/is this on track to finish by/i)).toBeInTheDocument();
  });

  it('records a Yes and navigates to the recorded page with state', async () => {
    ctxHolder.current = ctx();
    respondMock.mockResolvedValueOnce({
      outcome: 'recorded',
      recorded_value: 'yes',
      recorded_at: '2026-07-16T00:00:00Z',
      milestone_status: 'in_progress',
    });
    renderWithRouter(<MilestoneRespondPage />);

    await userEvent.click(screen.getByRole('button', { name: /yes, on track/i }));

    expect(respondMock).toHaveBeenCalledWith('alert-1', 'yes');
    expect(navigateMock).toHaveBeenCalledWith('/milestone/recorded', {
      replace: true,
      state: { recorded_value: 'yes', recorded_at: '2026-07-16T00:00:00Z' },
    });
  });

  it('routes a 410 (no longer current) to the inactive page', async () => {
    ctxHolder.current = ctx();
    respondMock.mockRejectedValueOnce(
      new PortalApiError('TOKEN_EXPIRED', 'gone', 410),
    );
    renderWithRouter(<MilestoneRespondPage />);

    await userEvent.click(screen.getByRole('button', { name: /will be delayed/i }));

    expect(navigateMock).toHaveBeenCalledWith('/milestone/unavailable', {
      replace: true,
    });
  });

  it('shows an inline error on an unexpected failure', async () => {
    ctxHolder.current = ctx();
    respondMock.mockRejectedValueOnce(new PortalApiError('UNKNOWN', 'boom', 500));
    renderWithRouter(<MilestoneRespondPage />);

    await userEvent.click(screen.getByRole('button', { name: /yes, on track/i }));

    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
