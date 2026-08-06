import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Step1CompanyInfo } from '../Step1CompanyInfo';
import type { VendorBidContext } from '../../../types/portal';
import { makePortalBidPackage, makeVendorBidContext } from '../../../test/fixtures';

function buildCtx(desired: string | null): VendorBidContext {
  return makeVendorBidContext({
    bid_package: makePortalBidPackage({ desired_start_date: desired }),
  });
}

const ctxRef: { current: VendorBidContext } = { current: buildCtx(null) };

vi.mock('../../../hooks/useBidContext', () => ({
  useBidContext: () => ctxRef.current,
}));

vi.mock('../../../services/portalApi', () => ({
  downloadProjectDocument: vi.fn(),
}));

// Step1CompanyInfo calls useToast(); avoid wiring a full provider in unit tests.
vi.mock('@/components/ui/Toast/useToast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

interface RenderOpts {
  desired?: string | null;
  proposed?: string | null;
  onUpdateProposedStartDate?: (v: string | null) => void;
}

function renderStep1(opts: RenderOpts = {}) {
  ctxRef.current = buildCtx(opts.desired ?? null);
  return render(
    <Step1CompanyInfo
      onNext={vi.fn()}
      onSaveDraft={vi.fn()}
      proposedStartDate={opts.proposed ?? null}
      onUpdateProposedStartDate={opts.onUpdateProposedStartDate ?? vi.fn()}
      sowAttestedName=""
      onUpdateSowAttestation={vi.fn()}
    />,
  );
}

describe('Step1CompanyInfo — proposed_start_date picker', () => {
  it('renders a Proposed start date input', () => {
    renderStep1({ desired: '2026-09-15' });
    expect(screen.getByLabelText(/Proposed start date/i)).toBeInTheDocument();
  });

  it('shows the picker even when the package has no desired date', () => {
    renderStep1({ desired: null });
    expect(screen.getByLabelText(/Proposed start date/i)).toBeInTheDocument();
  });

  it('marks the input required when the package has a desired date', () => {
    renderStep1({ desired: '2026-09-15' });
    const input = screen.getByLabelText(/Proposed start date/i) as HTMLInputElement;
    expect(input.required).toBe(true);
  });

  it('does NOT mark the input required when the package has no desired date', () => {
    renderStep1({ desired: null });
    const input = screen.getByLabelText(/Proposed start date/i) as HTMLInputElement;
    expect(input.required).toBe(false);
  });

  it('renders the prefilled value passed in via props', () => {
    renderStep1({ desired: '2026-09-15', proposed: '2026-09-15' });
    const input = screen.getByLabelText(/Proposed start date/i) as HTMLInputElement;
    expect(input.value).toBe('2026-09-15');
  });

  it('calls onUpdateProposedStartDate when the date is edited', () => {
    const onUpdate = vi.fn();
    renderStep1({
      desired: '2026-09-15',
      proposed: '2026-09-15',
      onUpdateProposedStartDate: onUpdate,
    });
    const input = screen.getByLabelText(/Proposed start date/i) as HTMLInputElement;
    // fireEvent.change is reliable for type="date" in JSDOM where
    // userEvent.type goes through keydown and date inputs strip
    // partial / non-ISO values.
    fireEvent.change(input, { target: { value: '2026-10-01' } });
    expect(onUpdate).toHaveBeenCalledWith('2026-10-01');
  });
});
