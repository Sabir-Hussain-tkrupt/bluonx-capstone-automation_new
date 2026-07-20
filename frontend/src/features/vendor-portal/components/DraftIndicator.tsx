import { Check, Loader2 } from 'lucide-react';
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
        <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
      )}
      {tone === 'amber' && (
        <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-warning-500" />
      )}
      {tone === 'green' && (
        <Check className="h-3 w-3" aria-hidden="true" />
      )}
      <span>{label}</span>
    </div>
  );
}
