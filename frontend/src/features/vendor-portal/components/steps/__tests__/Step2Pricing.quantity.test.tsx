import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { Step2Pricing } from '../Step2Pricing';
import type { BidFormState, FormLineItem, PortalBidTemplate } from '../../../types/portal';

const structuredTemplate: PortalBidTemplate = {
  id: 'tpl',
  name: 'Sitework',
  is_lump_sum: false,
  items: [],
};

const templateRef: { current: PortalBidTemplate } = { current: structuredTemplate };

vi.mock('../../../hooks/useBidContext', () => ({
  useBidContext: () => ({ bid_template: templateRef.current }),
}));

function unitPriceLine(overrides: Partial<FormLineItem> = {}): FormLineItem {
  return {
    template_item_id: 'li1',
    description: 'Excavation',
    item_type: 'unit_price',
    unit_of_measure: 'CY',
    sort_order: 1,
    quantity: null,
    unit_price: null,
    lump_sum_amount: null,
    ...overrides,
  };
}

function buildState(line: FormLineItem): BidFormState {
  return {
    step: 2,
    completedSteps: [1],
    dirty: false,
    companyInfo: { vendor_notes: '', proposed_start_date: null, sow_attested_name: '' },
    pricing: { total_amount: null, line_items: [line] },
    attachments: [],
    submissionId: null,
  };
}

function renderStep2(line: FormLineItem, onNext = vi.fn()) {
  templateRef.current = structuredTemplate;
  render(
    <Step2Pricing
      state={buildState(line)}
      onSetLumpTotal={vi.fn()}
      onUpdateLineItem={vi.fn()}
      onNext={onNext}
      onBack={vi.fn()}
      onSaveDraft={vi.fn()}
    />,
  );
  return { onNext };
}

describe('Step2Pricing — quantity must be greater than zero', () => {
  it('blocks Next and shows the error when a unit-price line has quantity 0', () => {
    const { onNext } = renderStep2(
      unitPriceLine({ quantity: 0, unit_price: 100 }),
    );
    fireEvent.click(screen.getByRole('button', { name: /Next: Documents/i }));
    expect(onNext).not.toHaveBeenCalled();
    expect(
      screen.getAllByText(/Quantity must be greater than zero/i).length,
    ).toBeGreaterThan(0);
  });

  it('allows Next when quantity is greater than zero', () => {
    const { onNext } = renderStep2(
      unitPriceLine({ quantity: 5, unit_price: 100 }),
    );
    fireEvent.click(screen.getByRole('button', { name: /Next: Documents/i }));
    expect(onNext).toHaveBeenCalledTimes(1);
  });
});
