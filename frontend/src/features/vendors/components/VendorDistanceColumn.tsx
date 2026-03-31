/**
 * Inline distance display for vendor lists.
 *
 * Shows distance in miles with one decimal, or "N/A" when coordinates
 * are missing.
 */

interface VendorDistanceColumnProps {
  distanceMiles: number | null | undefined;
}

export function VendorDistanceColumn({ distanceMiles }: VendorDistanceColumnProps) {
  if (distanceMiles == null) {
    return <span className="text-secondary-400">N/A</span>;
  }

  return <span>{distanceMiles.toFixed(1)} mi</span>;
}
