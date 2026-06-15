import { useState } from 'react';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { Alert } from '@/components/ui/Alert';
import { Skeleton } from '@/components/ui/Skeleton';
import { FormField } from '@/components/ui/FormField';
import { useAwardValidation } from '@/features/bids/hooks/useAwardValidation';
import { cn } from '@/utils/cn';
import type { PreAwardCheck, PreAwardSeverity } from '@/features/bids/types';

const JUSTIFICATION_MAX = 2000;
const INSTRUCTIONS_MAX = 2000;

export interface AwardDialogProps {
  /** Candidate submission; also drives the lazy validation fetch. Null = closed. */
  bidSubmissionId: string | null;
  vendorName: string;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (args: {
    has_override: boolean;
    override_justification?: string;
    instructions?: string;
  }) => void;
  isSubmitting: boolean;
  serverError?: string | null;
}

/**
 * Task 9.2 award + validation override dialog. Renders the 9.1 validation
 * preview and gates the confirm action client-side (the server re-validates and
 * is the final truth):
 *   - any `block`  → confirm disabled (cannot award), no justification field.
 *   - any `warn`   → required justification; confirm disabled until non-empty.
 *   - all clean    → confirm enabled, no justification field.
 */
export function AwardDialog({
  bidSubmissionId,
  vendorName,
  isOpen,
  onClose,
  onConfirm,
  isSubmitting,
  serverError,
}: AwardDialogProps) {
  const { data: result, isLoading, error } = useAwardValidation(
    isOpen ? bidSubmissionId : null,
  );
  // Fresh per submission — the page remounts this dialog via `key`.
  const [justification, setJustification] = useState('');
  const [instructions, setInstructions] = useState('');

  const hasBlocking = result?.has_blocking ?? false;
  const hasWarnings = result?.has_warnings ?? false;
  const justificationMissing = hasWarnings && justification.trim().length === 0;

  const confirmDisabled =
    isLoading ||
    !!error ||
    !result ||
    hasBlocking ||
    justificationMissing ||
    isSubmitting;

  const handleConfirm = () => {
    if (confirmDisabled) return;
    onConfirm({
      has_override: hasWarnings,
      override_justification: hasWarnings ? justification.trim() : undefined,
      instructions: instructions.trim() || undefined,
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Award — ${vendorName}`}
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleConfirm}
            disabled={confirmDisabled}
            isLoading={isSubmitting}
          >
            Confirm Award
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {serverError && (
          <Alert variant="danger" title="Could not create award">
            {serverError}
          </Alert>
        )}

        {isLoading && (
          <div className="space-y-2">
            <Skeleton height="24px" />
            <Skeleton height="96px" />
          </div>
        )}

        {error && !isLoading && (
          <Alert variant="danger" title="Could not load validation">
            Unable to run pre-award validation. Please try again.
          </Alert>
        )}

        {result && !isLoading && (
          <>
            {hasBlocking ? (
              <Alert variant="danger" title="This vendor cannot be awarded">
                One or more blocking checks failed. Resolve them before awarding.
              </Alert>
            ) : hasWarnings ? (
              <Alert variant="warning" title="Validation warnings">
                Awarding requires a documented justification for the warnings below.
              </Alert>
            ) : (
              <Alert variant="success" title="All checks passed">
                No issues found. You can award this vendor.
              </Alert>
            )}

            <ul className="space-y-2">
              {result.checks.map((check) => (
                <CheckRow key={check.check} check={check} />
              ))}
            </ul>

            {hasWarnings && !hasBlocking && (
              <FormField
                label="Override justification"
                htmlFor="award-justification"
                required
                hint="Explain why you're proceeding past the warnings. Stored on the award for audit."
              >
                <textarea
                  id="award-justification"
                  rows={4}
                  maxLength={JUSTIFICATION_MAX}
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                  className={cn(
                    'w-full rounded-lg border bg-white px-3 py-2 text-sm transition-colors',
                    'focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none',
                    'placeholder:text-secondary-400 border-secondary-300',
                  )}
                  placeholder="e.g. Vendor's insurance renewal is in progress; certificate expected before mobilization."
                />
                <p className="text-right text-xs text-secondary-400">
                  {justification.length}/{JUSTIFICATION_MAX}
                </p>
              </FormField>
            )}

            {!hasBlocking && (
              <FormField
                label="Instructions (optional)"
                htmlFor="award-instructions"
                hint="PM guidance for the vendor (mobilization, site access, etc.). Included in the award email."
              >
                <textarea
                  id="award-instructions"
                  rows={4}
                  maxLength={INSTRUCTIONS_MAX}
                  value={instructions}
                  onChange={(e) => setInstructions(e.target.value)}
                  className={cn(
                    'w-full rounded-lg border bg-white px-3 py-2 text-sm transition-colors',
                    'focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none',
                    'placeholder:text-secondary-400 border-secondary-300',
                  )}
                  placeholder="e.g. Mobilize the week of July 1; check in with the site super at the north gate."
                />
                <p className="text-right text-xs text-secondary-400">
                  {instructions.length}/{INSTRUCTIONS_MAX}
                </p>
              </FormField>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}

const SEVERITY_STYLES: Record<
  PreAwardSeverity,
  { dot: string; label: string; labelText: string }
> = {
  block: { dot: 'bg-danger-500', label: 'text-danger-700', labelText: 'Block' },
  warn: { dot: 'bg-warning-500', label: 'text-warning-700', labelText: 'Warning' },
  pass: { dot: 'bg-success-500', label: 'text-secondary-500', labelText: 'Pass' },
  skipped: { dot: 'bg-secondary-300', label: 'text-secondary-400', labelText: 'Skipped' },
};

function CheckRow({ check }: { check: PreAwardCheck }) {
  const s = SEVERITY_STYLES[check.severity];
  const muted = check.severity === 'pass' || check.severity === 'skipped';
  return (
    <li
      className={cn(
        'flex items-start gap-3 rounded-lg border px-3 py-2 text-sm',
        check.severity === 'block' && 'border-danger-100 bg-danger-50/60',
        check.severity === 'warn' && 'border-warning-100 bg-warning-50/60',
        muted && 'border-secondary-200 bg-white',
      )}
    >
      <span className={cn('mt-1.5 h-2 w-2 shrink-0 rounded-full', s.dot)} aria-hidden />
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-secondary-900">
            {formatCheckName(check.check)}
          </span>
          <span className={cn('text-xs font-semibold uppercase tracking-wide', s.label)}>
            {s.labelText}
          </span>
        </div>
        <p className={cn('mt-0.5', muted ? 'text-secondary-500' : 'text-secondary-700')}>
          {check.message}
        </p>
      </div>
    </li>
  );
}

function formatCheckName(check: string): string {
  return check
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}
