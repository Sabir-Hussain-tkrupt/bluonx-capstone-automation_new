import { useState } from 'react';
import { Alert, Button, Card } from '@/components/ui';
import { useBidContext } from '../../hooks/useBidContext';
import { computeGrandTotal, computeLineTotal } from '../../hooks/useBidFormState';
import type { BidFormState, StepIndex } from '../../types/portal';
import { formatCurrency } from '../../utils/currency';
import { ConfirmSubmitDialog } from '../ConfirmSubmitDialog';

export interface Step4ReviewProps {
  state: BidFormState;
  onEdit: (step: StepIndex) => void;
  onBack: () => void;
  onSaveDraft: () => void;
  onSubmit: () => Promise<void>;
  submitting: boolean;
  /** When true (deadline expired mid-session), Submit is locked. */
  disabled?: boolean;
  /** Revision mode — switches submit copy to "Submit Revised Bid". */
  isRevision?: boolean;
}

export function Step4Review({
  state,
  onEdit,
  onBack,
  onSaveDraft,
  onSubmit,
  submitting,
  disabled = false,
  isRevision = false,
}: Step4ReviewProps) {
  const { vendor, project, task, bid_template } = useBidContext();
  const [showConfirm, setShowConfirm] = useState(false);

  const grandTotal = bid_template.is_lump_sum
    ? state.pricing.total_amount ?? 0
    : computeGrandTotal(state.pricing.line_items);

  const canSubmit = grandTotal > 0 && !disabled;

  async function handleConfirm() {
    await onSubmit();
    setShowConfirm(false);
  }

  return (
    <div className="flex flex-col gap-6">
      <Alert variant="info" title="Review your bid before submitting">
        Double-check every section. Use the Edit links to go back and make changes.
      </Alert>

      {/* Company info summary */}
      <Card
        title="Company Info"
        actions={
          <Button type="button" variant="ghost" size="sm" onClick={() => onEdit(1)}>
            Edit
          </Button>
        }
        padding="md"
      >
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-secondary-500">Company</dt>
            <dd className="font-medium text-secondary-900">{vendor.company_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-secondary-500">Contact</dt>
            <dd className="font-medium text-secondary-900">
              {vendor.primary_contact_name}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-secondary-500">Project</dt>
            <dd className="font-medium text-secondary-900">{project.name}</dd>
          </div>
          <div>
            <dt className="text-xs text-secondary-500">Task</dt>
            <dd className="font-medium text-secondary-900">{task.name}</dd>
          </div>
        </dl>
      </Card>

      {/* Pricing summary */}
      <Card
        title="Pricing"
        actions={
          <Button type="button" variant="ghost" size="sm" onClick={() => onEdit(2)}>
            Edit
          </Button>
        }
        padding="md"
      >
        {bid_template.is_lump_sum ? (
          <div className="flex items-center justify-between">
            <span className="text-sm text-secondary-600">Total Bid Amount</span>
            <span className="text-lg font-bold text-primary-700 tabular-nums">
              {formatCurrency(state.pricing.total_amount)}
            </span>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-secondary-200 text-sm">
              <thead>
                <tr className="text-left text-xs font-semibold tracking-wide text-secondary-600 uppercase">
                  <th className="py-2">Item</th>
                  <th className="py-2 text-right">Qty</th>
                  <th className="py-2 text-right">Unit Price / LS</th>
                  <th className="py-2 text-right">Line Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-secondary-100">
                {state.pricing.line_items.map((item) => {
                  const lineTotal = computeLineTotal(item);
                  return (
                    <tr key={item.template_item_id}>
                      <td className="py-2 pr-2 text-secondary-900">
                        {item.description}
                        <span className="ml-2 text-xs text-secondary-400">
                          {item.unit_of_measure ?? ''}
                        </span>
                      </td>
                      <td className="py-2 text-right text-secondary-700 tabular-nums">
                        {item.item_type === 'unit_price' ? item.quantity ?? '—' : '—'}
                      </td>
                      <td className="py-2 text-right text-secondary-700 tabular-nums">
                        {item.item_type === 'unit_price'
                          ? formatCurrency(item.unit_price)
                          : formatCurrency(item.lump_sum_amount)}
                      </td>
                      <td className="py-2 text-right font-semibold text-secondary-900 tabular-nums">
                        {formatCurrency(lineTotal)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td colSpan={3} className="py-2 pt-4 text-right text-sm font-semibold text-secondary-700">
                    Grand Total
                  </td>
                  <td className="py-2 pt-4 text-right text-lg font-bold text-primary-700 tabular-nums">
                    {formatCurrency(grandTotal)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </Card>

      {/* Notes & Attachments summary */}
      <Card
        title="Notes & Attachments"
        actions={
          <Button type="button" variant="ghost" size="sm" onClick={() => onEdit(3)}>
            Edit
          </Button>
        }
        padding="md"
      >
        <div className="flex flex-col gap-4">
          {state.companyInfo.vendor_notes ? (
            <div>
              <p className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
                Notes to Owner
              </p>
              <p className="mt-1 whitespace-pre-wrap text-sm text-secondary-700">
                {state.companyInfo.vendor_notes}
              </p>
            </div>
          ) : (
            <p className="text-sm text-secondary-500">No notes added.</p>
          )}

          {state.attachments.length === 0 ? (
            <p className="text-sm text-secondary-500">No attachments uploaded.</p>
          ) : (
            <div>
              <p className="mb-2 text-xs font-medium tracking-wide text-secondary-500 uppercase">
                Uploaded Files
              </p>
              <ul className="divide-y divide-secondary-100">
                {state.attachments.map((att) => (
                  <li
                    key={att.id}
                    className="flex items-center justify-between py-2 text-sm"
                  >
                    <span className="font-medium text-secondary-900">{att.name}</span>
                    <span className="text-xs text-secondary-500 tabular-nums">
                      {(att.size / (1024 * 1024)).toFixed(2)} MB
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Card>

      {disabled ? (
        <Alert variant="danger" title="Bid deadline has passed">
          Submissions are locked. Your draft has been saved but cannot be submitted.
        </Alert>
      ) : grandTotal <= 0 ? (
        <Alert variant="warning" title="Grand total must be greater than zero">
          Go back to the Pricing step and enter valid amounts before submitting.
        </Alert>
      ) : null}

      <div className="flex flex-col-reverse items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:gap-2">
          <Button type="button" variant="ghost" onClick={onBack}>
            ← Back
          </Button>
          <Button type="button" variant="outline" onClick={onSaveDraft}>
            Save Draft
          </Button>
        </div>
        <Button
          type="button"
          variant="primary"
          onClick={() => setShowConfirm(true)}
          disabled={!canSubmit || submitting}
        >
          {isRevision ? 'Submit Revised Bid' : 'Submit Bid'}
        </Button>
      </div>

      <ConfirmSubmitDialog
        isOpen={showConfirm}
        onClose={() => setShowConfirm(false)}
        onConfirm={handleConfirm}
        grandTotal={grandTotal}
        projectName={project.name}
        submitting={submitting}
        isRevision={isRevision}
      />
    </div>
  );
}
