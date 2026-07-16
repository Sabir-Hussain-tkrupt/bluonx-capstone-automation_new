import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { MilestoneRecordedPage } from '../MilestoneRecordedPage';

describe('MilestoneRecordedPage', () => {
  it('echoes the recorded answer + date from router state', () => {
    renderWithRouter(<MilestoneRecordedPage />, {
      initialEntries: [
        {
          pathname: '/milestone/recorded',
          state: { recorded_value: 'yes', recorded_at: '2026-07-15T00:00:00Z' },
        },
      ],
    });
    expect(screen.getByText('Response recorded')).toBeInTheDocument();
    expect(screen.getByText(/“Yes”/)).toBeInTheDocument();
  });

  it('falls back to generic copy without state', () => {
    renderWithRouter(<MilestoneRecordedPage />, {
      initialEntries: ['/milestone/recorded'],
    });
    expect(screen.getByText('Response recorded')).toBeInTheDocument();
    expect(
      screen.getByText(/your response has been recorded/i),
    ).toBeInTheDocument();
  });
});
