import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Card } from '@/components/ui';
import { ROUTES } from '@/constants/routes';
import { useMilestoneContext } from '../hooks/useMilestoneContext';
import { respondToMilestone } from '../services/portalApi';
import { PortalApiError, type MilestoneCheckType } from '../types/portal';

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/** The single question + button labels for each check kind. */
function questionFor(
  checkType: MilestoneCheckType,
  endDate: string,
): { prompt: string; yes: string; no: string } {
  switch (checkType) {
    case 'start':
      return {
        prompt: 'Has this work started?',
        yes: 'Yes, it has started',
        no: 'No, not yet',
      };
    case 'completion':
      return {
        prompt: 'Is this work complete?',
        yes: 'Yes, it is complete',
        no: 'No, not yet',
      };
    case 'progress':
    default:
      return {
        prompt: `Is this on track to finish by ${formatDate(endDate)}?`,
        yes: 'Yes, on track',
        no: 'No, it will be delayed',
      };
  }
}

/**
 * The milestone check-in itself: one plain question, two buttons. Reached only
 * with a live milestone session (behind VendorPortalGuard). The answer is
 * recorded server-side; on success we replace to the "recorded" page so Back
 * can't re-submit a now-spent link.
 */
export function MilestoneRespondPage() {
  const navigate = useNavigate();
  const {
    milestone_alert_id,
    milestone_name,
    project_name,
    task_name,
    check_type,
    end_date,
  } = useMilestoneContext();

  const [submitting, setSubmitting] = useState<'yes' | 'no' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const q = questionFor(check_type, end_date);

  const answer = async (value: 'yes' | 'no') => {
    if (submitting) return;
    setSubmitting(value);
    setError(null);
    try {
      const res = await respondToMilestone(milestone_alert_id, value);
      navigate(ROUTES.PORTAL_MILESTONE_RECORDED, {
        replace: true,
        state: {
          recorded_value: res.recorded_value,
          recorded_at: res.recorded_at,
        },
      });
    } catch (err) {
      if (err instanceof PortalApiError && err.status === 410) {
        // Cycle bumped / milestone resolved between opening and answering.
        navigate(ROUTES.PORTAL_MILESTONE_INACTIVE, { replace: true });
        return;
      }
      if (err instanceof PortalApiError && err.status === 401) {
        // The global 401 handler routes to /bid/expired; show copy meanwhile.
        setError(
          'Your session has expired. Please click the link in your email again to continue.',
        );
      } else {
        setError(
          'Something went wrong. Please try again, or contact your project manager.',
        );
      }
      setSubmitting(null);
    }
  };

  return (
    <div className="mx-auto max-w-xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="text-center">
        <p className="text-sm text-secondary-600">
          {project_name} · {task_name}
        </p>
        <h1 className="mt-1 text-2xl font-bold text-secondary-900 sm:text-3xl">
          {milestone_name}
        </h1>
      </div>

      <Card padding="md" className="mt-8">
        <p className="text-center text-lg font-semibold text-secondary-900">
          {q.prompt}
        </p>

        {error && (
          <div className="mt-4">
            <Alert variant="danger" title="Could not record your answer">
              {error}
            </Alert>
          </div>
        )}

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-center">
          <Button
            type="button"
            variant="primary"
            onClick={() => answer('yes')}
            isLoading={submitting === 'yes'}
            disabled={submitting !== null}
          >
            {q.yes}
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => answer('no')}
            isLoading={submitting === 'no'}
            disabled={submitting !== null}
          >
            {q.no}
          </Button>
        </div>
      </Card>

      <p className="mt-6 text-center text-xs text-secondary-500">
        Your project manager will see your answer right away. You can close this
        window when you are done.
      </p>
    </div>
  );
}
