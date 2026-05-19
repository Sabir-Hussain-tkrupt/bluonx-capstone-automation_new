import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RevisionInactivePage } from '../RevisionInactivePage';

describe('RevisionInactivePage', () => {
  it('renders the revision-inactive error copy', () => {
    render(<RevisionInactivePage />);
    expect(
      screen.getByText('This revision request is no longer active'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/your original bid remains in consideration/i),
    ).toBeInTheDocument();
  });
});
