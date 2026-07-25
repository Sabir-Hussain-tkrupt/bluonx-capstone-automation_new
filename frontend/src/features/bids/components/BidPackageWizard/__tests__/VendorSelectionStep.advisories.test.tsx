/**
 * Advisories on the vendor selection step.
 *
 * An advisory is a non-blocking caution (e.g. insurance lapses before the
 * project's estimated end): the vendor stays qualified and selectable, but the
 * PM should see the note. It is rendered distinctly from PM-created flags and
 * from the disqualification reasons shown in the excluded list.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { VendorSelectionStep } from '../VendorSelectionStep';
import type { QualifiedVendor } from '@/features/bids/types';

const useQualifiedVendorsMock = vi.fn();
vi.mock('@/features/bids/hooks/useQualifiedVendors', () => ({
  useQualifiedVendors: () => useQualifiedVendorsMock(),
}));

function makeVendor(overrides: Partial<QualifiedVendor> = {}): QualifiedVendor {
  return {
    vendor_id: 'v-1',
    company_name: 'Acme Grading',
    primary_contact: { id: 'c-1', full_name: 'Dana Reed', email: 'dana@acme.com', phone: null },
    contact_warning: null,
    distance_miles: 12.3,
    insurance_expiration_date: '2026-08-01',
    insurance_days_remaining: 60,
    bonding_capacity: 500000,
    max_active_jobs: 5,
    current_active_jobs: 1,
    available_capacity: 4,
    onboarding_status: 'complete',
    has_unresolved_flags: false,
    unresolved_flag_count: 0,
    flag_reasons: [],
    qualification_status: 'qualified',
    disqualification_reasons: [],
    advisories: [],
    ...overrides,
  };
}

function mockResponse(qualified: QualifiedVendor[], disqualified: QualifiedVendor[] = []) {
  useQualifiedVendorsMock.mockReturnValue({
    data: {
      task_id: 't-1',
      task_name: 'Grading',
      trade_name: 'Grading',
      project_id: 'p-1',
      project_name: 'Proj',
      filter_criteria: {
        radius_miles: 75, trade_id: 'tr-1', trade_name: 'Grading',
        min_bonding: null, insurance_cutoff_date: '2026-12-01',
      },
      qualified_vendors: qualified,
      disqualified_vendors: disqualified,
      total_qualified: qualified.length,
      total_disqualified: disqualified.length,
      warnings: [],
    },
    isLoading: false,
    error: null,
  });
}

const props = {
  taskId: 't-1',
  data: { vendorSelections: [] },
  onUpdate: vi.fn(),
  onNext: vi.fn(),
  onBack: vi.fn(),
};

describe('VendorSelectionStep advisories', () => {
  beforeEach(() => vi.clearAllMocks());

  it('marks a qualified vendor that carries an advisory', () => {
    mockResponse([
      makeVendor({ advisories: ['insurance_lapses_before_project_end'] }),
    ]);

    renderWithRouter(<VendorSelectionStep {...props} />);

    // The row keeps the vendor (still qualified/selectable) and shows a caution
    // whose tooltip names the advisory in readable form.
    const indicator = screen.getByTitle(/insurance lapses before project end/i);
    expect(indicator).toBeInTheDocument();
  });

  it('shows an Advisories section with the advisory when the row is expanded', async () => {
    const user = userEvent.setup();
    mockResponse([
      makeVendor({ advisories: ['insurance_lapses_before_project_end'] }),
    ]);

    renderWithRouter(<VendorSelectionStep {...props} />);

    // Expand the vendor row (the company name toggles it).
    await user.click(screen.getByText('Acme Grading'));

    expect(screen.getByText(/^Advisories$/)).toBeInTheDocument();
    expect(
      screen.getByText(/insurance lapses before project end/i),
    ).toBeInTheDocument();
  });

  it('shows no advisory indicator when there are none', () => {
    mockResponse([makeVendor({ advisories: [] })]);

    renderWithRouter(<VendorSelectionStep {...props} />);

    expect(
      screen.queryByTitle(/insurance lapses before project end/i),
    ).not.toBeInTheDocument();
  });

  it('keeps an expired vendor in the disqualified list, not as an advisory', async () => {
    const user = userEvent.setup();
    mockResponse(
      [],
      [
        makeVendor({
          vendor_id: 'v-2',
          company_name: 'Lapsed Co',
          qualification_status: 'disqualified',
          disqualification_reasons: ['insurance_expired'],
          advisories: [],
        }),
      ],
    );

    renderWithRouter(<VendorSelectionStep {...props} />);

    // Reveal the disqualified section.
    await user.click(screen.getByRole('button', { name: /disqualified vendor/i }));

    expect(screen.getByText('Lapsed Co')).toBeInTheDocument();
    expect(screen.getByText(/insurance expired/i)).toBeInTheDocument();
  });
});
