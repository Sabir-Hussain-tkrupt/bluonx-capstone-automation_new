import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { VendorDistanceColumn } from '../VendorDistanceColumn';

describe('VendorDistanceColumn', () => {
  it('formats distance correctly', () => {
    renderWithRouter(<VendorDistanceColumn distanceMiles={45.3} />);
    expect(screen.getByText('45.3 mi')).toBeInTheDocument();
  });

  it('rounds to one decimal place', () => {
    renderWithRouter(<VendorDistanceColumn distanceMiles={12.789} />);
    expect(screen.getByText('12.8 mi')).toBeInTheDocument();
  });

  it('shows 0.0 mi for zero distance', () => {
    renderWithRouter(<VendorDistanceColumn distanceMiles={0} />);
    expect(screen.getByText('0.0 mi')).toBeInTheDocument();
  });

  it('shows N/A for null distance', () => {
    renderWithRouter(<VendorDistanceColumn distanceMiles={null} />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });

  it('shows N/A for undefined distance', () => {
    renderWithRouter(<VendorDistanceColumn distanceMiles={undefined} />);
    expect(screen.getByText('N/A')).toBeInTheDocument();
  });
});
