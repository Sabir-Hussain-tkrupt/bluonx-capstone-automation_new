import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { VendorMapDisplay } from '../VendorMapDisplay';

// Mock @vis.gl/react-google-maps
vi.mock('@vis.gl/react-google-maps', () => ({
  APIProvider: ({ children }: { children: React.ReactNode }) => <div data-testid="api-provider">{children}</div>,
  Map: ({ children, ...props }: any) => <div data-testid="google-map" {...props}>{children}</div>,
  AdvancedMarker: ({ children, ...props }: any) => (
    <div data-testid="map-marker" data-lat={props.position?.lat} data-lng={props.position?.lng}>
      {children}
    </div>
  ),
  useApiIsLoaded: vi.fn(() => true),
  useMap: vi.fn(() => null),
}));

import { useApiIsLoaded } from '@vis.gl/react-google-maps';
const mockUseApiIsLoaded = vi.mocked(useApiIsLoaded);

const PROJECT_LOCATION = { lat: 30.2672, lng: -97.7431 };

const VENDORS = [
  {
    id: 'v1',
    company_name: 'Nearby Vendor',
    latitude: 30.30,
    longitude: -97.74,
    distance_miles: 2.3,
  },
  {
    id: 'v2',
    company_name: 'Far Vendor',
    latitude: 29.42,
    longitude: -98.49,
    distance_miles: 73.5,
  },
];

const VENDOR_NO_COORDS = {
  id: 'v3',
  company_name: 'No Coords Vendor',
  latitude: null,
  longitude: null,
  distance_miles: null,
};

describe('VendorMapDisplay', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseApiIsLoaded.mockReturnValue(true);
  });

  it('renders without crashing', () => {
    renderWithRouter(
      <VendorMapDisplay
        projectLocation={PROJECT_LOCATION}
        vendors={VENDORS}
        radiusMiles={75}
      />
    );

    expect(screen.getByTestId('google-map')).toBeInTheDocument();
  });

  it('shows vendor markers for each vendor with coordinates', () => {
    renderWithRouter(
      <VendorMapDisplay
        projectLocation={PROJECT_LOCATION}
        vendors={VENDORS}
        radiusMiles={75}
      />
    );

    const markers = screen.getAllByTestId('map-marker');
    // 2 vendor markers + 1 project marker = 3
    expect(markers.length).toBeGreaterThanOrEqual(2);
  });

  it('shows project marker distinctly', () => {
    renderWithRouter(
      <VendorMapDisplay
        projectLocation={PROJECT_LOCATION}
        vendors={[]}
        radiusMiles={75}
      />
    );

    // Even with no vendors, the project marker should exist
    const markers = screen.getAllByTestId('map-marker');
    expect(markers.length).toBeGreaterThanOrEqual(1);
  });

  it('handles missing project coordinates with fallback message', () => {
    renderWithRouter(
      <VendorMapDisplay
        projectLocation={null}
        vendors={VENDORS}
        radiusMiles={75}
      />
    );

    expect(screen.getByText(/location not set/i)).toBeInTheDocument();
    expect(screen.queryByTestId('google-map')).not.toBeInTheDocument();
  });

  it('handles API load failure with fallback UI', () => {
    mockUseApiIsLoaded.mockReturnValue(false);

    renderWithRouter(
      <VendorMapDisplay
        projectLocation={PROJECT_LOCATION}
        vendors={VENDORS}
        radiusMiles={75}
      />
    );

    expect(screen.getByText(/map unavailable/i)).toBeInTheDocument();
  });

  it('excludes vendors without coordinates from markers', () => {
    renderWithRouter(
      <VendorMapDisplay
        projectLocation={PROJECT_LOCATION}
        vendors={[...VENDORS, VENDOR_NO_COORDS]}
        radiusMiles={75}
      />
    );

    const markers = screen.getAllByTestId('map-marker');
    // Should NOT have a marker for vendor_no_coords
    const nullMarker = markers.find(
      (m) => m.getAttribute('data-lat') === 'null'
    );
    expect(nullMarker).toBeUndefined();
  });

  it('renders with empty vendor list', () => {
    renderWithRouter(
      <VendorMapDisplay
        projectLocation={PROJECT_LOCATION}
        vendors={[]}
        radiusMiles={75}
      />
    );

    expect(screen.getByTestId('google-map')).toBeInTheDocument();
  });
});
