/**
 * VendorForm: insurance expiry is not an input, and 'complete' is edit-only.
 *
 * insurance_expiration_date is a derived mirror of the vendor's valid
 * insurance certificates, recomputed on every document upload and delete. A
 * hand-typed value claimed coverage no certificate backed (turning the
 * pre-award "uninsurable" block into a pass) and was silently overwritten by
 * the next document change.
 *
 * 'complete' requires a valid certificate, and documents are stored under
 * {vendor_id}/..., so none can exist before the vendor row does.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithRouter } from '@/test/test-utils';
import { VendorForm } from '../VendorForm';
import type { Vendor } from '@/features/vendors/api/vendor.queries';

vi.mock('@/features/vendors/hooks/useTrades', () => ({
  useTrades: () => ({ data: [] }),
}));

const existingVendor = {
  id: 'v-1',
  company_name: 'Acme Grading',
  address: '1 Main St',
  city: 'Austin',
  state: 'TX',
  zip_code: '78701',
  latitude: 30.26,
  longitude: -97.74,
  insurance_expiration_date: '2027-01-01',
  insurance_coverage_amount: 1000000,
  bonding_capacity: null,
  max_active_jobs: null,
  current_active_jobs: 0,
  onboarding_status: 'partial',
  status: 'active',
  notes: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  deleted_at: null,
} as unknown as Vendor;

const baseProps = {
  isOpen: true,
  onClose: vi.fn(),
  onSubmit: vi.fn(),
};

function onboardingSelect(): HTMLSelectElement {
  // FormField's label is not wired to the Select via htmlFor, so find the
  // combobox by its contents instead: only this one offers "Partial".
  const select = screen
    .getAllByRole('combobox')
    .find((el) => within(el).queryByRole('option', { name: /^partial$/i }));
  if (!select) throw new Error('Onboarding status select not found');
  return select as HTMLSelectElement;
}

describe('VendorForm insurance expiry', () => {
  beforeEach(() => vi.clearAllMocks());

  it('offers no insurance expiration input when creating', () => {
    renderWithRouter(<VendorForm {...baseProps} />);
    expect(screen.queryByText(/insurance expiration/i)).not.toBeInTheDocument();
  });

  it('offers no insurance expiration input when editing either', () => {
    renderWithRouter(<VendorForm {...baseProps} vendor={existingVendor} />);
    expect(screen.queryByText(/insurance expiration/i)).not.toBeInTheDocument();
  });

  it('still offers the coverage amount, which nothing derives', () => {
    renderWithRouter(<VendorForm {...baseProps} vendor={existingVendor} />);
    expect(screen.getByText(/insurance coverage/i)).toBeInTheDocument();
  });
});

describe('VendorForm onboarding status options', () => {
  beforeEach(() => vi.clearAllMocks());

  it('hides Complete when creating', () => {
    renderWithRouter(<VendorForm {...baseProps} />);
    const select = onboardingSelect();

    expect(within(select).getByRole('option', { name: /pending/i })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: /partial/i })).toBeInTheDocument();
    expect(within(select).queryByRole('option', { name: /complete/i })).not.toBeInTheDocument();
  });

  it('explains why, rather than just omitting the option', () => {
    renderWithRouter(<VendorForm {...baseProps} />);
    expect(screen.getByText(/after uploading an insurance certificate/i)).toBeInTheDocument();
  });

  it('offers Complete when editing', () => {
    renderWithRouter(<VendorForm {...baseProps} vendor={existingVendor} />);
    const select = onboardingSelect();

    expect(within(select).getByRole('option', { name: /complete/i })).toBeInTheDocument();
  });
});
