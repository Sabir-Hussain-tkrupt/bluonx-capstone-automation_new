import { formatCurrency } from '@/lib/format';
import { cn } from '@/utils/cn';
import type { BidSubmissionLineItem } from '@/features/bids/types';

export interface BidLineItemsTableProps {
  items: BidSubmissionLineItem[];
}

function TypeBadge({ type }: { type: 'lump_sum' | 'unit_price' }) {
  return (
    <span
      className={cn(
        'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
        type === 'lump_sum'
          ? 'bg-info-100 text-info-700'
          : 'bg-secondary-100 text-secondary-700',
      )}
    >
      {type === 'lump_sum' ? 'Lump Sum' : 'Unit Price'}
    </span>
  );
}

function formatQuantity(value: number | null): string {
  if (value == null) return '—';
  return Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 });
}

/** Responsive bid-line-items table — extracted from BidSubmissionDetailModal
 * so it can be reused for inline expansion in the Compare route table. */
export function BidLineItemsTable({ items }: BidLineItemsTableProps) {
  if (items.length === 0) {
    return (
      <div className="rounded-md border border-secondary-200 px-4 py-8 text-center text-sm text-secondary-500">
        No line items submitted.
      </div>
    );
  }

  const grandTotal = items.reduce(
    (sum, li) => sum + Number(li.line_total ?? 0),
    0,
  );

  return (
    <div className="overflow-hidden rounded-md border border-secondary-200">
      {/* Mobile cards */}
      <div className="space-y-3 p-3 md:hidden">
        {items.map((li, idx) => (
          <div
            key={li.id}
            className="rounded-md border border-secondary-200 bg-white p-3"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-xs text-secondary-500">#{idx + 1}</p>
                <p className="text-sm font-semibold text-secondary-900">
                  {li.description}
                </p>
              </div>
              <TypeBadge type={li.item_type} />
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <dt className="text-secondary-500">UoM</dt>
              <dd className="text-right text-secondary-900">{li.unit_of_measure ?? '—'}</dd>
              <dt className="text-secondary-500">Qty</dt>
              <dd className="text-right text-secondary-900">
                {li.item_type === 'unit_price' ? formatQuantity(li.quantity) : '—'}
              </dd>
              <dt className="text-secondary-500">Unit Price ($)</dt>
              <dd className="text-right text-secondary-900">
                {li.item_type === 'unit_price' && li.unit_price != null
                  ? formatCurrency(li.unit_price)
                  : '—'}
              </dd>
              <dt className="text-secondary-500">Lump Sum ($)</dt>
              <dd className="text-right text-secondary-900">
                {li.item_type === 'lump_sum' && li.lump_sum_amount != null
                  ? formatCurrency(li.lump_sum_amount)
                  : '—'}
              </dd>
              <dt className="text-secondary-500">Line Total</dt>
              <dd className="text-right font-semibold text-secondary-900">
                {formatCurrency(li.line_total)}
              </dd>
            </dl>
          </div>
        ))}
        <div className="flex items-center justify-between rounded-md bg-secondary-50 px-3 py-2">
          <span className="text-sm text-secondary-700">Grand Total</span>
          <span className="text-base font-bold text-primary-600">
            {formatCurrency(grandTotal)}
          </span>
        </div>
      </div>

      {/* Desktop table */}
      <div className="hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead className="bg-secondary-50 text-xs uppercase tracking-wider text-secondary-500">
            <tr>
              <th className="px-4 py-3 text-left font-medium">#</th>
              <th className="px-4 py-3 text-left font-medium">Description</th>
              <th className="px-4 py-3 text-left font-medium">Type</th>
              <th className="px-4 py-3 text-left font-medium">UoM</th>
              <th className="px-4 py-3 text-right font-medium">Qty</th>
              <th className="px-4 py-3 text-right font-medium">Unit Price ($)</th>
              <th className="px-4 py-3 text-right font-medium">Lump Sum ($)</th>
              <th className="px-4 py-3 text-right font-medium">Line Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-secondary-100 bg-white">
            {items.map((li, idx) => (
              <tr key={li.id}>
                <td className="px-4 py-3 text-secondary-500">{idx + 1}</td>
                <td className="px-4 py-3 font-semibold text-secondary-900">
                  {li.description}
                </td>
                <td className="px-4 py-3">
                  <TypeBadge type={li.item_type} />
                </td>
                <td className="px-4 py-3 text-secondary-700">
                  {li.unit_of_measure ?? '—'}
                </td>
                <td className="px-4 py-3 text-right text-secondary-900">
                  {li.item_type === 'unit_price' ? formatQuantity(li.quantity) : '—'}
                </td>
                <td className="px-4 py-3 text-right text-secondary-900">
                  {li.item_type === 'unit_price' && li.unit_price != null
                    ? formatCurrency(li.unit_price)
                    : '—'}
                </td>
                <td className="px-4 py-3 text-right text-secondary-900">
                  {li.item_type === 'lump_sum' && li.lump_sum_amount != null
                    ? formatCurrency(li.lump_sum_amount)
                    : '—'}
                </td>
                <td className="px-4 py-3 text-right font-medium text-secondary-900">
                  {formatCurrency(li.line_total)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot className="bg-secondary-50">
            <tr>
              <td colSpan={7} className="px-4 py-3 text-right text-sm text-secondary-700">
                Grand Total
              </td>
              <td className="px-4 py-3 text-right text-base font-bold text-primary-600">
                {formatCurrency(grandTotal)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
