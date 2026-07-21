import { api } from '@/lib/api';
import { API_ENDPOINTS } from '@/constants/api';

// ─── Mutation Input Types ─────────────────────────────────────────────

export interface CreateVendorInput {
  company_name: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  insurance_expiration_date?: string;
  insurance_coverage_amount?: number;
  bonding_capacity?: number;
  max_active_jobs?: number;
  onboarding_status?: 'pending' | 'partial' | 'complete';
  status?: 'active' | 'inactive' | 'suspended';
  notes?: string;
  contacts?: ContactInlineInput[];
  trade_ids?: string[];
}

export interface ContactInlineInput {
  full_name: string;
  email: string;
  phone?: string;
  title?: string;
  is_primary?: boolean;
}

export interface UpdateVendorInput {
  id: string;
  company_name?: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  insurance_expiration_date?: string;
  insurance_coverage_amount?: number;
  bonding_capacity?: number;
  max_active_jobs?: number;
  onboarding_status?: 'pending' | 'partial' | 'complete';
  status?: 'active' | 'inactive' | 'suspended';
  notes?: string;
}

export interface CreateContactInput {
  vendorId: string;
  full_name: string;
  email: string;
  phone?: string;
  title?: string;
  is_primary?: boolean;
}

export interface UpdateContactInput {
  vendorId: string;
  contactId: string;
  full_name?: string;
  email?: string;
  phone?: string;
  title?: string;
  is_primary?: boolean;
}

export interface BulkTradeInput {
  vendorId: string;
  trade_ids: string[];
}

export interface VendorImportRow {
  company_name: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  contact_name?: string;
  contact_email?: string;
  contact_phone?: string;
  contact_title?: string;
  notes?: string;
}

export interface VendorImportResponse {
  created: number;
  errors: { row: number; message: string }[];
}

// ─── FastAPI Write Operations ─────────────────────────────────────────

export async function createVendor(input: CreateVendorInput) {
  const { data } = await api.post(API_ENDPOINTS.VENDORS, input);
  return data;
}

export async function updateVendor({ id, ...input }: UpdateVendorInput) {
  const { data } = await api.patch(API_ENDPOINTS.VENDOR(id), input);
  return data;
}

export async function deleteVendor(id: string): Promise<void> {
  await api.delete(API_ENDPOINTS.VENDOR(id));
}

// ─── Contacts ─────────────────────────────────────────────────────────

export async function createContact({ vendorId, ...input }: CreateContactInput) {
  const { data } = await api.post(API_ENDPOINTS.VENDOR_CONTACTS(vendorId), input);
  return data;
}

export async function updateContact({ vendorId, contactId, ...input }: UpdateContactInput) {
  const { data } = await api.patch(API_ENDPOINTS.VENDOR_CONTACT(vendorId, contactId), input);
  return data;
}

export async function deleteContact(vendorId: string, contactId: string): Promise<void> {
  await api.delete(API_ENDPOINTS.VENDOR_CONTACT(vendorId, contactId));
}

// ─── Trades ───────────────────────────────────────────────────────────

export async function addVendorTrades({ vendorId, trade_ids }: BulkTradeInput) {
  const { data } = await api.post(API_ENDPOINTS.VENDOR_TRADES_ENDPOINT(vendorId), { trade_ids });
  return data;
}

export async function removeVendorTrade(vendorId: string, tradeId: string): Promise<void> {
  await api.delete(API_ENDPOINTS.VENDOR_TRADE(vendorId, tradeId));
}

// ─── CSV Import ───────────────────────────────────────────────────────

export async function importVendorsCSV(rows: VendorImportRow[]): Promise<VendorImportResponse> {
  // The server imports row by row, geocoding each address, so a full 100-row
  // batch can run well past the 30s default. Timing out here would report a
  // failure while the server carried on creating vendors.
  const { data } = await api.post<VendorImportResponse>(
    API_ENDPOINTS.VENDOR_IMPORT,
    { rows },
    { timeout: 180_000 },
  );
  return data;
}
