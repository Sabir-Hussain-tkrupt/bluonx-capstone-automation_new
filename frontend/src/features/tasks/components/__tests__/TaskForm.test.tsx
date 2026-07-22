import { describe, it, expect, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { TaskForm } from '../TaskForm';

const userEvent = userEventBase.setup({ delay: null });

const TRADES = [
  { id: 'trade-dev', name: 'Grading', phase: 'development', is_active: true },
  { id: 'trade-both', name: 'Engineering', phase: 'both', is_active: true },
  { id: 'trade-dd', name: 'Geotech', phase: 'due_diligence', is_active: true },
];

vi.mock('@/features/tasks/hooks/useTrades', () => ({
  useTrades: () => ({ data: TRADES }),
}));

function renderForm() {
  const onSubmit = vi.fn();
  renderWithRouter(<TaskForm isOpen onClose={() => {}} onSubmit={onSubmit} />);
  const [phase, trade, bidType] = screen.getAllByRole('combobox');
  const name = () => screen.getByRole('dialog').querySelector<HTMLInputElement>('input[name="name"]')!;
  const budget = () => screen.getByRole('dialog').querySelector<HTMLInputElement>('input[name="budget_estimate"]')!;
  return { onSubmit, phase, trade, bidType, name, budget };
}

describe('TaskForm bid type', () => {
  it('offers only Competitive and Internal, never Direct Assign', () => {
    const { bidType } = renderForm();

    expect(within(bidType).getByRole('option', { name: 'Competitive' })).toBeInTheDocument();
    expect(within(bidType).getByRole('option', { name: 'Internal' })).toBeInTheDocument();
    expect(within(bidType).queryByRole('option', { name: 'Direct Assign' })).not.toBeInTheDocument();
  });
});

describe('TaskForm trade dropdown', () => {
  it('is disabled until a phase is chosen', () => {
    const { trade } = renderForm();
    expect(trade).toBeDisabled();
  });

  it('lists only trades matching the selected phase (plus "both")', async () => {
    const { phase, trade } = renderForm();

    await userEvent.selectOptions(phase, 'development');

    expect(trade).toBeEnabled();
    expect(within(trade).getByRole('option', { name: 'Grading' })).toBeInTheDocument();
    expect(within(trade).getByRole('option', { name: 'Engineering' })).toBeInTheDocument();
    expect(within(trade).queryByRole('option', { name: 'Geotech' })).not.toBeInTheDocument();
  });
});

describe('TaskForm validation', () => {
  it('rejects a whitespace-only name', async () => {
    const { onSubmit, name } = renderForm();

    await userEvent.type(name(), '   ');
    await userEvent.click(screen.getByRole('button', { name: 'Create Task' }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('Task name is required (min 2 characters)')).toBeInTheDocument();
  });

  it('accepts a zero budget', async () => {
    const { onSubmit, phase, trade, bidType, name, budget } = renderForm();

    await userEvent.type(name(), 'Mass Grading');
    await userEvent.selectOptions(phase, 'development');
    await userEvent.selectOptions(trade, 'trade-dev');
    await userEvent.selectOptions(bidType, 'competitive');
    await userEvent.type(budget(), '0');
    await userEvent.click(screen.getByRole('button', { name: 'Create Task' }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Mass Grading', trade_id: 'trade-dev', bid_type: 'competitive', budget_estimate: 0 }),
    );
  });
});
