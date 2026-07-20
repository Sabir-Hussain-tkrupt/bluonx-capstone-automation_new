import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Pencil } from 'lucide-react';
import { Alert, Button, Card, Modal } from '@/components/ui';
import { ROUTES } from '@/constants/routes';
import { cn } from '@/utils/cn';
import { RevisionDeadline } from '../components/RevisionDeadline';
import { useBidContext } from '../hooks/useBidContext';
import { declineRevisionRequest } from '../services/portalApi';
import { PortalApiError } from '../types/portal';

const REASON_MAX = 500;

/**
 * Shown when the vendor enters via a revision magic link
 * (`bid_context.revision_context` present), before the bid form.
 * Re-rendered on refresh/back because it is a guarded route reading
 * the session-hydrated context — no extra round-trip.
 */
export function RevisionLandingPage() {
  const navigate = useNavigate();
  const { project, task, revision_context } = useBidContext();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Defensive: an initial-bid token must never see this screen.
  if (!revision_context) {
    return <Navigate to={ROUTES.PORTAL_FORM} replace />;
  }

  const closeDialog = () => {
    if (submitting) return;
    setDialogOpen(false);
    setError(null);
  };

  const handleConfirmDecline = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await declineRevisionRequest(
        revision_context.bid_revision_request_id,
        reason.trim() || undefined,
      );
      // replace: a now-dead token must not be re-declinable via Back.
      navigate(ROUTES.PORTAL_REVISION_DECLINED, { replace: true });
    } catch (err) {
      if (err instanceof PortalApiError && err.status === 410) {
        // Request cancelled/expired between open and decline.
        navigate(ROUTES.PORTAL_REVISION_INACTIVE, { replace: true });
        return;
      }
      if (err instanceof PortalApiError && err.status === 401) {
        setError(
          'Your session has expired. Please click the link in your email again to continue.',
        );
      } else {
        setError(
          'Something went wrong. Please try again, or contact your project manager.',
        );
      }
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="text-center">
        <div
          aria-hidden="true"
          className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-warning-100 text-warning-700"
        >
          <Pencil className="h-7 w-7" aria-hidden="true" />
        </div>
        <h1 className="mt-4 text-2xl font-bold text-secondary-900 sm:text-3xl">
          Revision Requested
        </h1>
        <p className="mt-2 text-sm text-secondary-600">
          {project.name} · {task.name}
        </p>
      </div>

      <Card padding="md" className="mt-8">
        <p className="text-xs font-medium tracking-wide text-secondary-500 uppercase">
          Note from the project manager
        </p>
        <blockquote className="mt-2 border-l-4 border-warning-300 bg-warning-50 px-4 py-3 text-sm whitespace-pre-wrap text-secondary-800">
          {revision_context.pm_note}
        </blockquote>

        <div className="mt-6">
          <RevisionDeadline deadline={revision_context.revision_deadline} />
        </div>
      </Card>

      <div className="mt-8 flex flex-col items-center gap-3">
        <Button
          type="button"
          variant="primary"
          onClick={() => navigate(ROUTES.PORTAL_FORM)}
        >
          Open Bid Form
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => setDialogOpen(true)}
        >
          Decline to Revise
        </Button>
      </div>

      <Modal
        isOpen={dialogOpen}
        onClose={closeDialog}
        title="Decline this revision request?"
        size="md"
        mobileCenter
        footer={
          <>
            <Button
              type="button"
              variant="ghost"
              onClick={closeDialog}
              disabled={submitting}
            >
              Keep Reviewing
            </Button>
            <Button
              type="button"
              variant="danger"
              onClick={handleConfirmDecline}
              isLoading={submitting}
            >
              Confirm Decline
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-secondary-600">
            Your original bid will remain in consideration. This cannot be
            undone.
          </p>

          {error && (
            <Alert variant="danger" title="Could not decline">
              {error}
            </Alert>
          )}

          <div>
            <label
              htmlFor="decline-reason"
              className="block text-sm font-medium text-secondary-700"
            >
              Reason (optional)
            </label>
            <textarea
              id="decline-reason"
              rows={4}
              maxLength={REASON_MAX}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              disabled={submitting}
              className={cn(
                'mt-1 w-full rounded-lg border border-secondary-300 bg-white px-3 py-2 text-sm transition-colors',
                'focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 focus:outline-none',
                'placeholder:text-secondary-400 disabled:opacity-60',
              )}
              placeholder="Help the project manager understand — e.g., scope changed, capacity full, etc."
            />
            <p className="text-right text-xs text-secondary-400">
              {reason.length}/{REASON_MAX}
            </p>
          </div>
        </div>
      </Modal>
    </div>
  );
}
