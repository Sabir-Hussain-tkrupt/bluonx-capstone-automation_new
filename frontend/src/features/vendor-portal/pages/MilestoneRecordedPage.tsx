import { useLocation } from 'react-router-dom';
import { PortalErrorPage } from './PortalErrorPage';

interface RecordedState {
  recorded_value?: 'yes' | 'no';
  recorded_at?: string;
}

function formatDate(iso?: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

/**
 * Page A — the check-in answer is recorded. Reached after a successful answer
 * or when the vendor re-opens an already-answered link. When the recorded value
 * + date are known (via router state), they are echoed back so the vendor sees
 * exactly what was captured.
 */
export function MilestoneRecordedPage() {
  const { state } = useLocation();
  const { recorded_value, recorded_at } = (state as RecordedState | null) ?? {};
  const when = formatDate(recorded_at);

  const answerText =
    recorded_value === 'yes' ? 'Yes' : recorded_value === 'no' ? 'No' : null;

  const message = answerText
    ? `We recorded your answer${when ? ` on ${when}` : ''}: “${answerText}”. Thank you.`
    : 'Your response has been recorded. Thank you.';

  return (
    <PortalErrorPage
      variant="info"
      title="Response recorded"
      message={message}
      helpText="No further action is needed. You may close this window."
      icon={
        <svg viewBox="0 0 24 24" fill="none" className="h-8 w-8">
          <path
            d="M20 6L9 17l-5-5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      }
    />
  );
}
