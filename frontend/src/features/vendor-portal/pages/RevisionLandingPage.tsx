import { Navigate, useNavigate } from 'react-router-dom';
import { Button, Card } from '@/components/ui';
import { ROUTES } from '@/constants/routes';
import { RevisionDeadline } from '../components/RevisionDeadline';
import { useBidContext } from '../hooks/useBidContext';

/**
 * Shown when the vendor enters via a revision magic link
 * (`bid_context.revision_context` present), before the bid form.
 * Re-rendered on refresh/back because it is a guarded route reading
 * the session-hydrated context — no extra round-trip.
 */
export function RevisionLandingPage() {
  const navigate = useNavigate();
  const { project, task, revision_context } = useBidContext();

  // Defensive: an initial-bid token must never see this screen.
  if (!revision_context) {
    return <Navigate to={ROUTES.PORTAL_FORM} replace />;
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="text-center">
        <div
          aria-hidden="true"
          className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-warning-100 text-warning-700"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-7 w-7">
            <path
              d="M4 20h4l10.5-10.5a2.121 2.121 0 00-3-3L5 17v3z"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
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
        <p className="max-w-md text-center text-xs text-secondary-500">
          To decline this revision request instead, please use the
          “Decline to Revise” link in your email.
        </p>
      </div>
    </div>
  );
}
