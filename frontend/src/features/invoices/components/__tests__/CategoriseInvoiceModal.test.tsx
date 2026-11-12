import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEventBase from '@testing-library/user-event';
import { renderWithRouter } from '@/test/test-utils';
import { CategoriseInvoiceModal } from '../CategoriseInvoiceModal';
import type { Invoice } from '../../api/invoice.api';
import type { BudgetLine } from '@/features/budgets/types';

const userEvent = userEventBase.setup({ delay: null });
const mutate = vi.fn();

vi.mock('../../hooks/useInvoices', () => ({
  useCategoriseInvoice: () => ({ mutate, isPending: false }),
}));

const invoice = {
  id: 'inv-1', project_id: 'p', budget_line_id: null, vendor_id: null, payee_name: 'Law LLP',
  invoice_number: 'INV-2', invoice_date: null, amount: '1500.00', file_name: 'x.pdf', file_size: 1,
  status: 'received', notes: null, uploaded_by: 'u', created_at: null, budget_line_name: null,
  uploaded_by_name: null, vendor_name: null,
} as Invoice;

const tmLine = {
  id: 'l-att', name: 'Attorney', line_type: 'internal_tm', budget_amount: 3000, invoiced: 2000,
} as unknown as BudgetLine;
const bidLine = { id: 'l-bid', name: 'Clearing', line_type: 'bid_activity', budget_amount: 1, invoiced: 0 } as unknown as BudgetLine;

describe('CategoriseInvoiceModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists only internal T&M lines with what is left on each', () => {
    renderWithRouter(
      <CategoriseInvoiceModal projectId="p" invoice={invoice} lines={[tmLine, bidLine]} budgetStatus="baselined" onClose={vi.fn()} />,
    );
    expect(screen.getByRole('option', { name: /attorney — \$1,000\.00 left/i })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /clearing/i })).not.toBeInTheDocument();
  });

  it('previews the overage variance on a baselined budget and sends the line', async () => {
    renderWithRouter(
      <CategoriseInvoiceModal projectId="p" invoice={invoice} lines={[tmLine]} budgetStatus="baselined" onClose={vi.fn()} />,
    );
    await userEvent.selectOptions(screen.getByLabelText(/budget line/i), 'l-att');
    expect(screen.getByText(/over the line's allowance/i)).toBeInTheDocument();
    expect(screen.getByText('$500.00')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /send for approval/i }));
    expect(mutate).toHaveBeenCalledWith({ invoiceId: 'inv-1', lineId: 'l-att' }, expect.anything());
  });

  it('explains that a draft budget creates no variance', async () => {
    renderWithRouter(
      <CategoriseInvoiceModal projectId="p" invoice={invoice} lines={[tmLine]} budgetStatus="draft" onClose={vi.fn()} />,
    );
    await userEvent.selectOptions(screen.getByLabelText(/budget line/i), 'l-att');
    expect(screen.getByText(/no variance is created/i)).toBeInTheDocument();
  });
});
