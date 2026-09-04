/**
 * Table mobile card: valid markup and keyboard behaviour.
 *
 * Three defects pinned here:
 *  - The card title rendered in a <p>, so a column accessor returning a <div>
 *    (BidTemplateListPage's name column does) produced <div> inside <p>.
 *  - The whole card was wrapped in a <button>, so a row action button nested
 *    inside it. A screen reader cannot describe a button in a button and the
 *    focus order inside one is undefined.
 *  - Enter on a focused row action bubbled to the row handler, so the action
 *    fired AND the row click fired. Row actions only ever called
 *    stopPropagation on click, never on keydown. Both branches were affected,
 *    so the desktop <tr> is covered here too.
 */

import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Table } from '../Table';
import type { Column } from '../Table';

interface Row {
  id: string;
  name: string;
}

// Mirrors BidTemplateListPage: a title column whose accessor returns a block
// element, and an actions column of real buttons.
function makeColumns(onAction = vi.fn()): Column<Row>[] {
  return [
    {
      id: 'name',
      header: 'Name',
      accessor: (row) => (
        <div className="flex items-center gap-2">
          <span>{row.name}</span>
        </div>
      ),
    },
    {
      id: 'actions',
      header: '',
      accessor: () => (
        <div className="flex justify-end">
          <button type="button" aria-label="Row action" onClick={() => onAction()}>
            Act
          </button>
        </div>
      ),
    },
  ];
}

const data: Row[] = [{ id: '1', name: 'Acme' }];

function renderTable(onRowClick?: (row: Row) => void) {
  const onAction = vi.fn();
  const { container } = render(
    <Table
      columns={makeColumns(onAction)}
      data={data}
      keyExtractor={(r) => r.id}
      mobileTitle="name"
      onRowClick={onRowClick}
    />,
  );
  return { container, onAction };
}

// The desktop table and the mobile card list render from the same data, so
// every row appears twice. Only the card exposes a button role named after the
// row title, which is how it is addressed throughout.
function card() {
  return screen.getByRole('button', { name: 'Acme' });
}

describe('Table mobile card markup', () => {
  it('nests no button inside another button', () => {
    const { container } = renderTable(vi.fn());

    expect(container.querySelector('button button')).toBeNull();
  });

  it('nests no block element inside a paragraph', () => {
    const { container } = renderTable(vi.fn());

    expect(container.querySelector('p div')).toBeNull();
  });
});

describe('Table mobile card keyboard access', () => {
  it('exposes a button role named after the title column', () => {
    renderTable(vi.fn());

    expect(card()).toBeInTheDocument();
  });

  it('is reachable by keyboard', async () => {
    const user = userEvent.setup();
    renderTable(vi.fn());

    expect(card()).toHaveAttribute('tabindex', '0');

    await user.tab();
    expect(card()).toHaveFocus();
  });

  it('activates the row click on Enter', async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    renderTable(onRowClick);

    card().focus();
    await user.keyboard('{Enter}');

    expect(onRowClick).toHaveBeenCalledTimes(1);
    expect(onRowClick).toHaveBeenCalledWith(data[0]);
  });

  it('activates the row click on Space without scrolling the page', () => {
    const onRowClick = vi.fn();
    renderTable(onRowClick);

    // fireEvent returns false when the event was cancelled. Space must be
    // preventDefault'd or the page scrolls under the card.
    const notCancelled = fireEvent.keyDown(card(), { key: ' ' });

    expect(notCancelled).toBe(false);
    expect(onRowClick).toHaveBeenCalledTimes(1);
  });
});

describe('Table row actions do not trigger the row click', () => {
  it('runs only the action when a nested action is clicked', async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    const { onAction } = renderTable(onRowClick);

    await user.click(screen.getAllByRole('button', { name: 'Row action' })[0]);

    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('runs only the action on Enter over a nested action in the card', async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    const { onAction } = renderTable(onRowClick);

    // The card is the first tab stop, its action button the second.
    await user.tab();
    await user.tab();
    await user.keyboard('{Enter}');

    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onRowClick).not.toHaveBeenCalled();
  });

  it('runs only the action on Enter over a nested action in a desktop row', () => {
    const onRowClick = vi.fn();
    const { onAction } = renderTable(onRowClick);

    // The desktop <tr> carries the same onKeyDown, and keydown bubbles to it.
    const desktopAction = screen.getAllByRole('button', { name: 'Row action' })[1];
    fireEvent.keyDown(desktopAction, { key: 'Enter' });
    fireEvent.click(desktopAction);

    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onRowClick).not.toHaveBeenCalled();
  });
});

describe('Table mobile card without a row click', () => {
  it('renders a non-interactive wrapper', () => {
    renderTable(undefined);

    expect(screen.queryByRole('button', { name: 'Acme' })).not.toBeInTheDocument();
    // Only the two row-action buttons remain, one per view.
    expect(screen.getAllByRole('button')).toHaveLength(2);
    expect(screen.getAllByText('Acme')[0].closest('[tabindex]')).toBeNull();
  });
});

describe('Table plain row activation', () => {
  // The regression these pin: the nested-control guard compared the closest
  // interactive ancestor against the row itself. A desktop <tr> matches none
  // of the guard's selectors, so closest() returned null, null !== the row,
  // and every plain row click was silently swallowed. Clicking a row on any
  // list page did nothing at all above the md breakpoint.
  it('fires the row click when the mobile card itself is clicked', async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    renderTable(onRowClick);

    await user.click(card());

    expect(onRowClick).toHaveBeenCalledTimes(1);
    expect(onRowClick).toHaveBeenCalledWith(data[0]);
  });

  it('fires the row click when a desktop row is clicked', async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    const { container } = renderTable(onRowClick);

    const desktopRow = container.querySelector('tbody tr')!;
    await user.click(desktopRow);

    expect(onRowClick).toHaveBeenCalledTimes(1);
    expect(onRowClick).toHaveBeenCalledWith(data[0]);
  });

  it('fires the row click from a plain cell inside a desktop row', async () => {
    const user = userEvent.setup();
    const onRowClick = vi.fn();
    renderTable(onRowClick);

    // Index 1 is the desktop <td>; index 0 is the mobile card title.
    await user.click(screen.getAllByText('Acme')[1]);

    expect(onRowClick).toHaveBeenCalledTimes(1);
  });
});
