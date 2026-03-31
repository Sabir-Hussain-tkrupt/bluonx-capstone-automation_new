/**
 * Conditional Google Maps API provider.
 *
 * Wraps children in APIProvider when VITE_GOOGLE_MAPS_API_KEY is set.
 * When the key is absent, renders children without any Google Maps
 * context — all map components degrade to their fallback UI.
 */
import { APIProvider } from '@vis.gl/react-google-maps';

const API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY as string | undefined;

interface GoogleMapsProviderProps {
  children: React.ReactNode;
}

export function GoogleMapsProvider({ children }: GoogleMapsProviderProps) {
  if (!API_KEY) {
    return <>{children}</>;
  }

  return (
    <APIProvider apiKey={API_KEY} libraries={['places']}>
      {children}
    </APIProvider>
  );
}
