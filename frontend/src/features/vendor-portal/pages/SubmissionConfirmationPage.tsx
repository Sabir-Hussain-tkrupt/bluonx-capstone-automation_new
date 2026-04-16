import { useLocation } from 'react-router-dom';
import { Alert, Card } from '@/components/ui';
import { useBidContext } from '../hooks/useBidContext';
import { formatCurrency } from '../utils/currency';
import type { SubmitBidResult } from '../types/portal';

interface LocationState {
  result?: SubmitBidResult;
  grandTotal?: number;
}

export function SubmissionConfirmationPage() {
  const location = useLocation();
  const { vendor, project, task } = useBidContext();
  const state = (location.state ?? {}) as LocationState;
  const result = state.result;
  const grandTotal = state.grandTotal ?? 0;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="flex flex-col items-center text-center">
        <div
          aria-hidden="true"
          className="flex h-16 w-16 items-center justify-center rounded-full bg-success-100 text-success-600"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-9 w-9">
            <path
              d="M5 13l4 4L19 7"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <h1 className="mt-4 text-2xl font-bold text-secondary-900 sm:text-3xl">
          Bid submitted successfully
        </h1>
        <p className="mt-2 text-sm text-secondary-600">
          Thank you, {vendor.primary_contact_name}. Your bid has been received by BluOnX.
        </p>
      </div>

      <Card padding="md" className="mt-8">
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Confirmation Number
            </dt>
            <dd className="mt-1 font-mono text-base font-semibold text-primary-700">
              {result?.confirmation_number ?? '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Submitted At
            </dt>
            <dd className="mt-1 text-sm text-secondary-900">
              {result ? new Date(result.submitted_at).toLocaleString() : '—'}
            </dd>
          </div>
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
          <div className="sm:col-span-2">
            <dt className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
              Bid Total
            </dt>
            <dd className="mt-1 text-2xl font-bold text-primary-700 tabular-nums">
              {formatCurrency(grandTotal)}
            </dd>
          </div>
        </dl>
      </Card>

      <Alert variant="info" className="mt-6" title="What happens next">
        A confirmation email will be sent to {vendor.email}. BluOnX will contact you if additional information is needed.
      </Alert>
      
    </div>
  );
}
