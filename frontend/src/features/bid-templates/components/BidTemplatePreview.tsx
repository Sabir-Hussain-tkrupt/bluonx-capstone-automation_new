import type { BidTemplateItemInput } from '@/features/bid-templates/api/bid-template.mutations';

interface BidTemplatePreviewProps {
  isLumpSum: boolean;
  items: BidTemplateItemInput[];
}

export function BidTemplatePreview({ isLumpSum, items }: BidTemplatePreviewProps) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-secondary-900">Template Preview</h3>
        <p className="mt-1 text-xs text-secondary-500">
          Read-only preview of how vendors will see the bid form.
        </p>
      </div>

      <div className="rounded-lg border border-secondary-200 bg-white p-6">
        {isLumpSum ? (
          <div className="space-y-2">
            <label className="block text-sm font-medium text-secondary-700">
              Total Bid Amount
            </label>
            <div className="flex items-center gap-2">
              <span className="text-sm text-secondary-500">$</span>
              <input
                type="text"
                disabled
                placeholder="0.00"
                className="w-full max-w-xs rounded-lg border border-secondary-300 bg-secondary-50 px-3 py-2 text-sm text-secondary-400"
              />
            </div>
            <p className="text-xs text-secondary-400">
              Vendor enters a single lump sum total.
            </p>
          </div>
        ) : items.length === 0 ? (
          <p className="py-4 text-center text-sm text-secondary-400">
            Add line items above to see the preview.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-secondary-200 text-xs font-medium uppercase tracking-wider text-secondary-500">
                  <th className="pb-3 pr-4">#</th>
                  <th className="pb-3 pr-4">Description</th>
                  <th className="pb-3 pr-4">Type</th>
                  <th className="pb-3 pr-4">Unit</th>
                  <th className="pb-3 pr-4">Qty</th>
                  <th className="pb-3 pr-4">Unit Price</th>
                  <th className="pb-3 text-right">Line Total</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, index) => (
                  <tr
                    key={index}
                    className="border-b border-secondary-100 last:border-0"
                  >
                    <td className="py-3 pr-4 text-secondary-400">{index + 1}</td>
                    <td className="py-3 pr-4 font-medium text-secondary-900">
                      {item.description || '(empty)'}
                    </td>
                    <td className="py-3 pr-4 capitalize text-secondary-600">
                      {item.item_type === 'unit_price' ? 'Unit Price' : 'Lump Sum'}
                    </td>
                    <td className="py-3 pr-4 text-secondary-600">
                      {item.item_type === 'unit_price'
                        ? item.unit_of_measure || '-'
                        : '-'}
                    </td>
                    <td className="py-3 pr-4">
                      {item.item_type === 'unit_price' ? (
                        <input
                          disabled
                          type="text"
                          placeholder="0"
                          className="w-20 rounded border border-secondary-200 bg-secondary-50 px-2 py-1 text-sm text-secondary-400"
                        />
                      ) : (
                        <span className="text-secondary-400">-</span>
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      <input
                        disabled
                        type="text"
                        placeholder="$0.00"
                        className="w-24 rounded border border-secondary-200 bg-secondary-50 px-2 py-1 text-sm text-secondary-400"
                      />
                    </td>
                    <td className="py-3 text-right">
                      <span className="text-sm text-secondary-400">$0.00</span>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-secondary-300">
                  <td colSpan={6} className="py-3 pr-4 text-right font-semibold text-secondary-900">
                    Total
                  </td>
                  <td className="py-3 text-right font-semibold text-secondary-900">$0.00</td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
