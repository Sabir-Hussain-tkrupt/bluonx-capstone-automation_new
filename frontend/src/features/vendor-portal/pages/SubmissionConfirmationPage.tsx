import { useLocation } from 'react-router-dom';
import { Check } from 'lucide-react';
import { Alert, Card } from '@/components/ui';
import { useBidContext } from '../hooks/useBidContext';
import { formatCurrency } from '../utils/currency';
import type { SubmitBidResult } from '../types/portal';

interface LocationState {
  result?: SubmitBidResult;
  grandTotal?: number;
  isRevision?: boolean;
}

function coerceTotal(
  result: SubmitBidResult | undefined,
  grandTotalFallback: number,
): number {
  // Prefer the authoritative amount the backend committed + echoed back.
  // `total_amount` arrives as a string over the wire (Pydantic Decimal)
  // but the type allows number | string | null, so coerce defensively.
  const raw = result?.total_amount;
  if (raw === null || raw === undefined || raw === '') return grandTotalFallback;
  const n = typeof raw === 'string' ? Number(raw) : raw;
  return Number.isFinite(n) ? n : grandTotalFallback;
}

export function SubmissionConfirmationPage() {
  const location = useLocation();
  const { vendor, project, task } = useBidContext();
  const state = (location.state ?? {}) as LocationState;
  const result = state.result;
  const isRevision = state.isRevision ?? false;
  const total = coerceTotal(result, state.grandTotal ?? 0);
  const submittedAt = result?.submitted_at
    ? new Date(result.submitted_at)
    : null;
  const emailRecipient = result?.vendor_email || vendor.email;
  const emailSent = result?.confirmation_email_sent ?? true;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="flex flex-col items-center text-center">
        <div
          aria-hidden="true"
          className="flex h-16 w-16 items-center justify-center rounded-full bg-success-100 text-success-600"
        >
          <Check className="h-9 w-9" aria-hidden="true" />
        </div>
        <h1 className="mt-4 text-2xl font-bold text-secondary-900 sm:text-3xl">
          {isRevision ? 'Revised Bid Submitted' : 'Bid submitted successfully'}
        </h1>
        <p className="mt-2 text-sm text-secondary-600">
          {isRevision ? (
            <>
              Your revised bid has been received. The project manager has been
              notified, and your original bid remains in the record.
            </>
          ) : (
            <>
              Thank you, {vendor.primary_contact_name}. Your bid has been
              received by BluOnX.
            </>
          )}
        </p>
      </div>

      <Card padding="md" className="mt-8">
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Project
            </dt>
            <dd className="mt-1 text-sm font-medium text-secondary-900">{project.name}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Task
            </dt>
            <dd className="mt-1 text-sm font-medium text-secondary-900">{task.name}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Submitted At
            </dt>
            <dd className="mt-1 text-sm text-secondary-900">
              {submittedAt ? submittedAt.toLocaleString() : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Bid Total
            </dt>
            <dd className="mt-1 text-2xl font-bold text-primary-700 tabular-nums">
              {formatCurrency(total)}
            </dd>
          </div>
        </dl>
      </Card>

      <Alert
        variant={emailSent ? 'info' : 'warning'}
        className="mt-6"
        title="What happens next"
      >
        {emailSent ? (
          <>
            A confirmation email has been sent to{' '}
            <span className="font-medium">{emailRecipient}</span>. You will be
            notified of the award decision.
          </>
        ) : (
          <>
            Your bid was recorded, but we could not deliver the confirmation
            email to{' '}
            <span className="font-medium">{emailRecipient}</span> right now.
            You will still be notified of the award decision.
          </>
        )}
      </Alert>
    </div>
  );
}
