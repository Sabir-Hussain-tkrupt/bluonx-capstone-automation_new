import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RevisionDeclinedPage } from '../RevisionDeclinedPage';

describe('RevisionDeclinedPage', () => {
  it('renders the revision-declined confirmation copy', () => {
    render(<RevisionDeclinedPage />);
    expect(screen.getByText('Revision Declined')).toBeInTheDocument();
    expect(
      screen.getByText(/your original bid remains in consideration/i),
    ).toBeInTheDocument();
  });
});
