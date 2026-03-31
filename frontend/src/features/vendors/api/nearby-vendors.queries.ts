import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';

// ─── Types ────────────────────────────────────────────────────────────

export interface NearbyVendor {
  id: string;
  company_name: string;
  city: string | null;
  state: string | null;
  latitude: number | null;
  longitude: number | null;
  status: string;
  distance_miles: number;
}

interface NearbyVendorParams {
  radius?: number;
  tradeId?: string;
}

// ─── API Call ─────────────────────────────────────────────────────────

export async function fetchNearbyVendors(
  projectId: string,
  params?: NearbyVendorParams,
): Promise<NearbyVendor[]> {
  const queryParams: Record<string, string | number> = {};

  if (params?.radius != null) queryParams.radius = params.radius;
  if (params?.tradeId) queryParams.trade_id = params.tradeId;

  const { data } = await api.get<NearbyVendor[]>(
    API_ENDPOINTS.NEARBY_VENDORS(projectId),
    { params: queryParams },
  );

  return data;
}
