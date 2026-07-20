/**
 * Google Map showing vendor locations relative to a project.
 *
 * Displays:
 * - Project marker (blue) at the project location
 * - Vendor markers (red) for each vendor with coordinates
 * - 75-mile radius circle around the project
 *
 * Graceful fallbacks:
 * - null project location → "Location not set" message
 * - API not loaded → "Map unavailable" message
 * - Vendors without coords → silently excluded
 */
import { useEffect, useRef } from 'react';
import { Home, MapPin } from 'lucide-react';
import { Map, AdvancedMarker, useApiIsLoaded, useMap } from '@vis.gl/react-google-maps';

const METERS_PER_MILE = 1609.344;

interface VendorPin {
  id: string;
  company_name: string;
  latitude: number | null;
  longitude: number | null;
  distance_miles: number | null;
}

interface VendorMapDisplayProps {
  projectLocation: { lat: number; lng: number } | null;
  vendors: VendorPin[];
  radiusMiles: number;
}

/** Inner component that draws the radius circle (needs the map instance). */
function RadiusCircle({
  center,
  radiusMiles,
}: {
  center: { lat: number; lng: number };
  radiusMiles: number;
}) {
  const map = useMap();
  const circleRef = useRef<google.maps.Circle | null>(null);

  useEffect(() => {
    if (!map) return;

    if (circleRef.current) {
      circleRef.current.setMap(null);
    }

    circleRef.current = new google.maps.Circle({
      map,
      center,
      radius: radiusMiles * METERS_PER_MILE,
      fillColor: '#3B82F6',
      fillOpacity: 0.08,
      strokeColor: '#3B82F6',
      strokeOpacity: 0.3,
      strokeWeight: 1,
    });

    return () => {
      if (circleRef.current) {
        circleRef.current.setMap(null);
        circleRef.current = null;
      }
    };
  }, [map, center, radiusMiles]);

  return null;
}

export function VendorMapDisplay({ projectLocation, vendors, radiusMiles }: VendorMapDisplayProps) {
  const apiIsLoaded = useApiIsLoaded();

  // Filter vendors that have valid coordinates
  const validVendors = vendors.filter(
    (v) => v.latitude != null && v.longitude != null,
  );

  if (!projectLocation) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-secondary-300 bg-secondary-50">
        <p className="text-sm text-secondary-500">Location not set — add an address to see the map</p>
      </div>
    );
  }

  if (!apiIsLoaded) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-secondary-300 bg-secondary-50">
        <p className="text-sm text-secondary-500">Map unavailable</p>
      </div>
    );
  }

  return (
    <div className="h-96 w-full overflow-hidden rounded-lg border border-secondary-200">
      <Map
        defaultCenter={projectLocation}
        defaultZoom={9}
        gestureHandling="cooperative"
        mapId="vendor-map"
        className="h-full w-full"
      >
        {/* Radius circle */}
        <RadiusCircle center={projectLocation} radiusMiles={radiusMiles} />

        {/* Project marker */}
        <AdvancedMarker
          position={projectLocation}
          title="Project Location"
        >
          <div className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-white bg-blue-600 shadow-lg">
            <Home className="h-4 w-4 text-white" aria-hidden="true" />
          </div>
        </AdvancedMarker>

        {/* Vendor markers */}
        {validVendors.map((vendor) => (
          <AdvancedMarker
            key={vendor.id}
            position={{ lat: vendor.latitude!, lng: vendor.longitude! }}
            title={`${vendor.company_name}${vendor.distance_miles != null ? ` — ${vendor.distance_miles.toFixed(1)} mi` : ''}`}
          >
            <div className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-white bg-red-500 shadow-md">
              <MapPin className="h-3 w-3 text-white" aria-hidden="true" />
            </div>
          </AdvancedMarker>
        ))}
      </Map>
    </div>
  );
}
