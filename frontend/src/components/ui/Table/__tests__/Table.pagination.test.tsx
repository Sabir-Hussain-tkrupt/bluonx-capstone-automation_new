import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Table } from '../Table';
import type { Column } from '../Table';

interface Row {
  id: string;
  name: string;
}

const columns: Column<Row>[] = [{ id: 'name', header: 'Name', accessor: 'name' }];

function renderTable(data: Row[], total: number, onPageChange = vi.fn(), page = 1) {
  render(
    <Table
      columns={columns}
      data={data}
      keyExtractor={(r) => r.id}
      pagination={{ page, pageSize: 25, total, onPageChange }}
    />,
  );
  return onPageChange;
}

describe('Table pagination on an empty page', () => {
  it('keeps the controls when a page is past the end of a non-empty result set', () => {
    // The regression: the empty-data branch used to return before rendering
    // the pagination bar, stranding anyone whose result set shrank while they
    // were on a later page. No Previous button meant no way back but a reload.
    renderTable([], 30, vi.fn(), 5);

    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous page' })).toBeEnabled();
  });

  it('offers an explicit way back to the first page', async () => {
    const onPageChange = renderTable([], 30, vi.fn(), 5);

    await userEvent.click(screen.getByRole('button', { name: 'Back to first page' }));

    expect(onPageChange).toHaveBeenCalledWith(1);
  });

  it('explains that the page is past the end rather than claiming no results', () => {
    renderTable([], 30, vi.fn(), 5);

    expect(screen.getByText('Nothing on this page')).toBeInTheDocument();
    expect(screen.getByText(/past the end of the 30 matching results/)).toBeInTheDocument();
  });

  it('shows the normal empty state when there genuinely are no results', () => {
    renderTable([], 0);

    expect(screen.getByText('No data found')).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Pagination' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Back to first page' })).not.toBeInTheDocument();
  });

  it('still renders pagination normally when the page has rows', () => {
    renderTable([{ id: '1', name: 'Acme' }], 30);

    expect(screen.getByRole('navigation', { name: 'Pagination' })).toBeInTheDocument();
    // Rendered twice: once in the mobile card view, once in the desktop table.
    expect(screen.getAllByText('Acme')).toHaveLength(2);
  });
});
