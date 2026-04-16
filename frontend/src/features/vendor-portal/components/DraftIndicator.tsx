import { cn } from '@/utils/cn';

export type DraftStatus = 'idle' | 'saving' | 'saved' | 'error';

export interface DraftIndicatorProps {
  status: DraftStatus;
  lastSavedAt: Date | null;
  dirty: boolean;
  className?: string;
}

function formatTime(d: Date): string {
  return d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

export function DraftIndicator({
  status,
  lastSavedAt,
  dirty,
  className,
}: DraftIndicatorProps) {
  let label: string;
  let tone: 'neutral' | 'amber' | 'green' | 'red';

  if (status === 'saving') {
    label = 'Saving draft…';
    tone = 'neutral';
  } else if (status === 'error') {
    label = 'Save failed — will retry';
    tone = 'red';
  } else if (dirty) {
    label = 'Unsaved changes';
    tone = 'amber';
  } else if (lastSavedAt) {
    label = `Draft saved at ${formatTime(lastSavedAt)}`;
    tone = 'green';
  } else {
    label = 'No draft saved yet';
    tone = 'neutral';
  }

  const toneClasses: Record<typeof tone, string> = {
    neutral: 'bg-secondary-100 text-secondary-700 border-secondary-200',
    amber: 'bg-warning-50 text-warning-700 border-warning-200',
    green: 'bg-success-50 text-success-700 border-success-200',
    red: 'bg-danger-50 text-danger-700 border-danger-200',
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium',
        toneClasses[tone],
        className,
      )}
    >
      {status === 'saving' && (
        <svg
          className="h-3 w-3 animate-spin"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
          <path
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            className="opacity-75"
          />
        </svg>
      )}
      {tone === 'amber' && (
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-warning-500" />
      )}
      {tone === 'green' && (
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-3 w-3" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M16.704 5.29a1 1 0 010 1.42l-8 8a1 1 0 01-1.42 0l-4-4a1 1 0 011.42-1.42L8 12.58l7.29-7.29a1 1 0 011.41 0z"
            clipRule="evenodd"
          />
        </svg>
      )}
      <span>{label}</span>
    </div>
  );
}
