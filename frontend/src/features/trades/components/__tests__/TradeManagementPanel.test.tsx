import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { TradeManagementPanel } from '../TradeManagementPanel';
import type { Trade, TradeUsage } from '../../types';

const userEvent = userEventBase.setup({ delay: null });
const deleteMutate = vi.fn();
let usage: TradeUsage | undefined;

const t = (id: string, name: string, parent: string | null = null): Trade => ({
  id,
  name,
  phase: 'development',
  is_active: true,
  parent_trade_id: parent,
  created_at: '',
  updated_at: '',
});
const trades = [t('e', 'Electrical'), t('ec', 'Commercial', 'e'), t('g', 'Grading')];

vi.mock('../../hooks/useTrades', () => ({
  useTrades: () => ({ data: trades, isLoading: false, isError: false, refetch: vi.fn() }),
}));
vi.mock('../../hooks/useCreateTrade', () => ({
  useCreateTrade: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('../../hooks/useTradeMutations', () => ({
  useTradeUsage: () => ({ data: usage, isLoading: false, isError: false }),
  useDeleteTrade: () => ({ mutate: deleteMutate, isPending: false }),
  useUpdateTrade: () => ({ mutate: vi.fn(), isPending: false }),
}));

const base: TradeUsage = {
  trade_id: 'x',
  tasks: 0,
  vendors: 0,
  task_templates: 0,
  bid_templates: 0,
  budget_template_lines: 0,
  variances: 0,
  subtrades: 0,
  total: 0,
  in_use: false,
  can_edit: true,
  can_delete: true,
};

describe('TradeManagementPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    usage = base;
  });

  it('lists subtrades under their trade', () => {
    renderWithRouter(<TradeManagementPanel />);
    expect(screen.getByRole('list', { name: /subtrades of electrical/i })).toHaveTextContent('Commercial');
    expect(screen.getByText(/2 active trades and 1 subtrade/i)).toBeInTheDocument();
  });

  it('refuses to delete a trade that is in use and says why', async () => {
    usage = { ...base, tasks: 3, vendors: 1, total: 4, in_use: true, can_edit: false, can_delete: false };
    renderWithRouter(<TradeManagementPanel />);
    await userEvent.click(screen.getByRole('button', { name: /actions for grading/i }));
    await userEvent.click(screen.getByRole('menuitem', { name: /delete/i }));
    expect(screen.getByText(/used by 3 tasks and 1 vendor/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^delete$/i })).not.toBeInTheDocument();
  });

  it('deletes an unused subtrade after confirming', async () => {
    renderWithRouter(<TradeManagementPanel />);
    await userEvent.click(screen.getByRole('button', { name: /actions for commercial/i }));
    await userEvent.click(screen.getByRole('menuitem', { name: /delete/i }));
    expect(screen.getByText(/not used anywhere/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    expect(deleteMutate).toHaveBeenCalledWith('ec', expect.anything());
  });

  it('opens the add-subtrade form from a trade', async () => {
    renderWithRouter(<TradeManagementPanel />);
    await userEvent.click(screen.getByRole('button', { name: /actions for electrical/i }));
    await userEvent.click(screen.getByRole('menuitem', { name: /add subtrade/i }));
    expect(screen.getByText(/add subtrade to electrical/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/^phase/i)).not.toBeInTheDocument();
  });

  it('locks editing when the trade is in use', async () => {
    usage = { ...base, vendors: 2, total: 2, in_use: true, can_edit: false, can_delete: false };
    renderWithRouter(<TradeManagementPanel />);
    await userEvent.click(screen.getByRole('button', { name: /actions for grading/i }));
    await userEvent.click(screen.getByRole('menuitem', { name: /edit/i }));
    expect(screen.getByText(/used by 2 vendors/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save changes/i })).toBeDisabled();
  });
});
