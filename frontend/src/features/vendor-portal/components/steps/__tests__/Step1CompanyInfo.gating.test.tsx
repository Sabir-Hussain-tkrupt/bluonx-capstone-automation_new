import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Step1CompanyInfo } from '../Step1CompanyInfo';
import type { VendorBidContext } from '../../../types/portal';
import {
  makePortalBidPackage,
  makePortalVendor,
  makeVendorBidContext,
} from '../../../test/fixtures';

function buildCtx(desired: string | null): VendorBidContext {
  return makeVendorBidContext({
    // The SoW attestation is only valid when it matches company_name, and the
    // tests below sign by typing 'Apex'. Set explicitly so the two stay in step.
    vendor: makePortalVendor({ company_name: 'Apex' }),
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

vi.mock('@/components/ui/Toast/useToast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

interface RenderOpts {
  desired?: string | null;
  proposed?: string | null;
  sow?: string;
}

function renderStep1(opts: RenderOpts = {}) {
  ctxRef.current = buildCtx(opts.desired ?? null);
  const onNext = vi.fn();
  render(
    <Step1CompanyInfo
      onNext={onNext}
      onSaveDraft={vi.fn()}
      proposedStartDate={opts.proposed ?? null}
      onUpdateProposedStartDate={vi.fn()}
      sowAttestedName={opts.sow ?? ''}
      onUpdateSowAttestation={vi.fn()}
    />,
  );
  return { onNext };
}

function clickNext() {
  fireEvent.click(screen.getByRole('button', { name: /Next: Pricing/i }));
}

describe('Step1CompanyInfo — Next gating', () => {
  it('blocks Next and surfaces an SoW error when the signature is missing', () => {
    const { onNext } = renderStep1({ desired: null, sow: '' });
    clickNext();
    expect(onNext).not.toHaveBeenCalled();
    expect(screen.getByText(/Please sign by typing your company name/i)).toBeInTheDocument();
  });

  it('blocks Next when a required proposed start date is blank, even if signed', () => {
    const { onNext } = renderStep1({ desired: '2026-09-15', proposed: null, sow: 'Apex' });
    clickNext();
    expect(onNext).not.toHaveBeenCalled();
    expect(screen.getByText(/Proposed start date is required/i)).toBeInTheDocument();
  });

  it('allows Next when signed and the required date is present', () => {
    const { onNext } = renderStep1({
      desired: '2026-09-15',
      proposed: '2026-09-20',
      sow: 'Apex',
    });
    clickNext();
    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it('allows Next when signed and no start date is required', () => {
    const { onNext } = renderStep1({ desired: null, proposed: null, sow: 'Apex' });
    clickNext();
    expect(onNext).toHaveBeenCalledTimes(1);
  });
});
