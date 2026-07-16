import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MilestoneLandingPage } from '../MilestoneLandingPage';
import { PortalApiError } from '../../types/portal';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
  useParams: () => ({ token: 'tok-1' }),
}));

const validateMock = vi.fn();
vi.mock('../../services/portalApi', () => ({
  validateMilestoneToken: (...a: unknown[]) => validateMock(...a),
}));

const setMilestoneSession = vi.fn();
vi.mock('../../context/VendorPortalContext', () => ({
  useVendorPortal: () => ({ setMilestoneSession }),
}));

const MS_CONTEXT = {
  milestone_alert_id: 'alert-1',
  milestone_id: 'ms-1',
  milestone_name: 'Rough Grading',
  project_name: 'Phoenix Park',
  task_name: 'Grading',
  vendor_company_name: 'Apex',
  check_type: 'progress' as const,
  end_date: '2026-08-01',
  cycle_number: 1,
};

describe('MilestoneLandingPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('stores the session and routes to the respond page on actionable', async () => {
    validateMock.mockResolvedValueOnce({
      outcome: 'actionable',
      jwt: 'jwt-1',
      milestone_context: MS_CONTEXT,
    });
    render(<MilestoneLandingPage />);

    await waitFor(() =>
      expect(setMilestoneSession).toHaveBeenCalledWith('jwt-1', MS_CONTEXT),
    );
    expect(navigateMock).toHaveBeenCalledWith('/milestone/respond', {
      replace: true,
    });
  });

  it('routes to the recorded page (with state) when already answered', async () => {
    validateMock.mockResolvedValueOnce({
      outcome: 'already_answered',
      recorded_value: 'yes',
      recorded_at: '2026-07-15T00:00:00Z',
    });
    render(<MilestoneLandingPage />);

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/milestone/recorded', {
        replace: true,
        state: { recorded_value: 'yes', recorded_at: '2026-07-15T00:00:00Z' },
      }),
    );
    expect(setMilestoneSession).not.toHaveBeenCalled();
  });

  it('routes a 410 to the no-longer-current page', async () => {
    validateMock.mockRejectedValueOnce(
      new PortalApiError('TOKEN_EXPIRED', 'stale', 410),
    );
    render(<MilestoneLandingPage />);

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/milestone/unavailable', {
        replace: true,
      }),
    );
  });

  it('routes a 404 to the invalid-link page', async () => {
    validateMock.mockRejectedValueOnce(
      new PortalApiError('TOKEN_INVALID', 'nope', 404),
    );
    render(<MilestoneLandingPage />);

    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/bid/invalid', { replace: true }),
    );
  });
});
