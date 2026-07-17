import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MilestoneNoLongerCurrentPage } from '../MilestoneNoLongerCurrentPage';

describe('MilestoneNoLongerCurrentPage', () => {
  it('renders the no-longer-current copy', () => {
    render(<MilestoneNoLongerCurrentPage />);
    expect(
      screen.getByText('This check-in is no longer current'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/the schedule for this milestone has changed/i),
    ).toBeInTheDocument();
  });
});
