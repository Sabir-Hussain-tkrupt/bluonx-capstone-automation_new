/**
 * LineItemsTable: the <colgroup> must contain nothing but <col> elements.
 *
 * The defect: same-line JSX comments after each <col /> ("<col /> {comment}")
 * leave the run of spaces between them as a text child, and whitespace text
 * nodes are not legal inside <colgroup>.
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import { LineItemsTable } from '../LineItemsTable';
import type { FormLineItem } from '../../../types/portal';

const items: FormLineItem[] = [
  {
    template_item_id: 'li1',
    description: 'Excavation',
    item_type: 'unit_price',
    unit_of_measure: 'CY',
    sort_order: 1,
    quantity: 10,
    unit_price: 100,
    lump_sum_amount: null,
  },
];

describe('LineItemsTable colgroup', () => {
  it('contains only col elements, no text nodes', () => {
    const { container } = render(
      <LineItemsTable items={items} onUpdate={vi.fn()} fieldErrors={{}} />,
    );

    const colgroup = container.querySelector('colgroup');
    expect(colgroup).not.toBeNull();

    const childNames = Array.from(colgroup!.childNodes).map((node) =>
      node.nodeType === Node.ELEMENT_NODE ? (node as Element).tagName : `#${node.nodeName}`,
    );

    expect(childNames.every((name) => name === 'COL')).toBe(true);
  });
});
