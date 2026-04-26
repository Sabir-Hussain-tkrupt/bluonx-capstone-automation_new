import { TextInput } from '@/components/ui';
import { cn } from '@/utils/cn';
import { computeLineTotal, computeGrandTotal } from '../../hooks/useBidFormState';
import type { FormLineItem } from '../../types/portal';
import { formatCurrency } from '../../utils/currency';

export interface LineItemsTableProps {
  items: FormLineItem[];
  onUpdate: (
    template_item_id: string,
    patch: Partial<Pick<FormLineItem, 'quantity' | 'unit_price' | 'lump_sum_amount'>>,
  ) => void;
  fieldErrors: Record<string, string | undefined>;
}

export function LineItemsTable({ items, onUpdate, fieldErrors }: LineItemsTableProps) {
  const grandTotal = computeGrandTotal(items);

  return (
    <div className="flex flex-col gap-4">
      {/* Desktop table */}
      <div className="hidden overflow-x-auto rounded-lg border border-secondary-200 md:block">
        <table className="min-w-full divide-y divide-secondary-200 text-sm">
          {/* Explicit column widths prevent input cells from being squeezed */}
          <colgroup>
            <col className="w-10" />     {/* # */}
            <col />                       {/* Description — fills remaining space */}
            <col className="w-28" />     {/* Type */}
            <col className="w-14" />     {/* UoM */}
            <col className="w-32" />     {/* Qty */}
            <col className="w-36" />     {/* Unit Price ($) */}
            <col className="w-36" />     {/* Lump Sum ($) */}
            <col className="w-32" />     {/* Line Total */}
          </colgroup>
          <thead className="bg-secondary-50">
            <tr className="text-left text-xs font-semibold tracking-wide text-secondary-600 uppercase">
              <th className="px-4 py-3">#</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">UoM</th>
              <th className="px-4 py-3 text-right">Qty</th>
              <th className="px-4 py-3 text-right">Unit Price ($)</th>
              <th className="px-4 py-3 text-right">Lump Sum ($)</th>
              <th className="px-4 py-3 text-right">Line Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-secondary-100 bg-white">
            {items.map((item, idx) => {
              const lineTotal = computeLineTotal(item);
              const isLump = item.item_type === 'lump_sum';
              const err = fieldErrors[item.template_item_id];
              return (
                <tr key={item.template_item_id} className={cn(err && 'bg-danger-50/40')}>
                  <td className="px-4 py-3 text-secondary-500">{idx + 1}</td>
                  <td className="px-4 py-3 font-medium text-secondary-900">
                    {item.description}
                    {err && <p className="mt-1 text-xs text-danger-600">{err}</p>}
                  </td>
                  <td className="px-4 py-3">
                    <TypeBadge type={item.item_type} />
                  </td>
                  <td className="px-4 py-3 text-secondary-600">
                    {item.unit_of_measure ?? '—'}
                  </td>
                  <td className="px-4 py-3">
                    {/* No leftAddon in table — column header already gives context */}
                    <TextInput
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step={100}
                      aria-label={`Quantity for ${item.description}`}
                      value={item.quantity ?? ''}
                      onChange={(e) =>
                        onUpdate(item.template_item_id, {
                          quantity: e.target.value === '' ? null : Number(e.target.value),
                        })
                      }
                      disabled={isLump}
                      size="sm"
                      className="text-right"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <TextInput
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step={100}
                      aria-label={`Unit price for ${item.description}`}
                      value={item.unit_price ?? ''}
                      onChange={(e) =>
                        onUpdate(item.template_item_id, {
                          unit_price: e.target.value === '' ? null : Number(e.target.value),
                        })
                      }
                      disabled={isLump}
                      size="sm"
                      className="text-right"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <TextInput
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step={1000}
                      aria-label={`Lump sum for ${item.description}`}
                      value={item.lump_sum_amount ?? ''}
                      onChange={(e) =>
                        onUpdate(item.template_item_id, {
                          lump_sum_amount: e.target.value === '' ? null : Number(e.target.value),
                        })
                      }
                      disabled={!isLump}
                      size="sm"
                      className="text-right"
                    />
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-secondary-900 tabular-nums">
                    {formatCurrency(lineTotal)}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot className="bg-secondary-50">
            <tr>
              <td colSpan={7} className="px-4 py-3 text-right text-sm font-semibold text-secondary-700">
                Grand Total
              </td>
              <td className="px-4 py-3 text-right text-base font-bold text-primary-700 tabular-nums">
                {formatCurrency(grandTotal)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Mobile cards */}
      <div className="flex flex-col gap-3 md:hidden">
        {items.map((item, idx) => {
          const lineTotal = computeLineTotal(item);
          const isLump = item.item_type === 'lump_sum';
          const err = fieldErrors[item.template_item_id];
          return (
            <div
              key={item.template_item_id}
              className={cn(
                'rounded-lg border bg-white p-4 shadow-sm',
                err ? 'border-danger-300' : 'border-secondary-200',
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs font-medium text-secondary-500">Item {idx + 1}</p>
                  <p className="text-sm font-semibold text-secondary-900">{item.description}</p>
                </div>
                <TypeBadge type={item.item_type} />
              </div>
              {err && <p className="mt-2 text-xs text-danger-600">{err}</p>}

              {isLump ? (
                <div className="mt-3">
                  <label className="text-xs font-medium text-secondary-500">Lump sum ($)</label>
                  <TextInput
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step="0.01"
                    value={item.lump_sum_amount ?? ''}
                    onChange={(e) =>
                      onUpdate(item.template_item_id, {
                        lump_sum_amount: e.target.value === '' ? null : Number(e.target.value),
                      })
                    }
                    leftAddon={<span>$</span>}
                    size="sm"
                  />
                </div>
              ) : (
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-secondary-500">
                      Qty ({item.unit_of_measure ?? '—'})
                    </label>
                    <TextInput
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step="0.01"
                      value={item.quantity ?? ''}
                      onChange={(e) =>
                        onUpdate(item.template_item_id, {
                          quantity: e.target.value === '' ? null : Number(e.target.value),
                        })
                      }
                      size="sm"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-secondary-500">Unit Price</label>
                    <TextInput
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step="0.01"
                      value={item.unit_price ?? ''}
                      onChange={(e) =>
                        onUpdate(item.template_item_id, {
                          unit_price: e.target.value === '' ? null : Number(e.target.value),
                        })
                      }
                      leftAddon={<span>$</span>}
                      size="sm"
                    />
                  </div>
                </div>
              )}

              <div className="mt-3 flex items-center justify-between border-t border-secondary-100 pt-3">
                <span className="text-xs text-secondary-500">Line Total</span>
                <span className="text-sm font-semibold text-secondary-900 tabular-nums">
                  {formatCurrency(lineTotal)}
                </span>
              </div>
            </div>
          );
        })}

        <div className="flex items-center justify-between rounded-lg bg-primary-50 px-4 py-3">
          <span className="text-sm font-semibold text-primary-700">Grand Total</span>
          <span className="text-base font-bold text-primary-700 tabular-nums">
            {formatCurrency(grandTotal)}
          </span>
        </div>
      </div>
    </div>
  );
}

function TypeBadge({ type }: { type: FormLineItem['item_type'] }) {
  const isLump = type === 'lump_sum';
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold',
        isLump ? 'bg-info-50 text-info-700' : 'bg-secondary-100 text-secondary-700',
      )}
    >
      {isLump ? 'Lump Sum' : 'Unit Price'}
    </span>
  );
}
