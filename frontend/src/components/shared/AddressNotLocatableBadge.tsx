import { MapPinOff } from 'lucide-react';

interface AddressNotLocatableBadgeProps {
  /** The record's stored address line. */
  address: string | null | undefined;
  /** The record's stored latitude. Null means geocoding never resolved it. */
  latitude: number | null | undefined;
  /** What the record is called in the warning text. */
  entity?: string;
}

/**
 * Shown next to an address that exists but has no coordinates.
 *
 * Derived entirely from persisted state (an address on file, no latitude), so
 * it needs no backend support and lights up for rows written before geocode
 * warnings existed. The save-time toast only reaches whoever performed the
 * write; this is how anyone else finds out later.
 *
 * "No address on file" and "address on file we could not locate" need
 * different actions from a PM (go get the address, versus go check the one we
 * have), so this deliberately renders nothing when there is no address at all.
 */
export function AddressNotLocatableBadge({
  address,
  latitude,
  entity = 'record',
}: AddressNotLocatableBadgeProps) {
  const hasAddress = !!address && address.trim().length > 0;
  if (!hasAddress || latitude != null) return null;

  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-warning-50 px-2 py-0.5 text-xs font-medium text-warning-700"
      title={`We couldn't locate this address on the map, so this ${entity} won't appear in distance-based vendor searches.`}
    >
      <MapPinOff className="h-3 w-3" aria-hidden="true" />
      Address not locatable
    </span>
  );
}
