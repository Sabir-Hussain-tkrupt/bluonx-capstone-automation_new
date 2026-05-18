import { useEffect, useState } from 'react';
import { cn } from '@/utils/cn';

export interface BidDeadlineCountdownProps {
  deadline: string; // ISO
  className?: string;
  /**
   * Heading copy. Defaults to "Bid deadline" (initial-bid path). In
   * revision mode the parent overrides this with "Revision deadline" so
   * the widget reflects revision_context.revision_deadline, not the
   * (irrelevant) package deadline.
   */
  label?: string;
}

interface RemainingTime {
  expired: boolean;
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
}

function compute(deadline: string): RemainingTime {
  const target = new Date(deadline).getTime();
  const now = Date.now();
  const diff = target - now;
  if (diff <= 0) {
    return { expired: true, days: 0, hours: 0, minutes: 0, seconds: 0 };
  }
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
  const minutes = Math.floor((diff / (1000 * 60)) % 60);
  const seconds = Math.floor((diff / 1000) % 60);
  return { expired: false, days, hours, minutes, seconds };
}

export function BidDeadlineCountdown({
  deadline,
  className,
  label = 'Bid deadline',
}: BidDeadlineCountdownProps) {
  const [remaining, setRemaining] = useState<RemainingTime>(() => compute(deadline));

  useEffect(() => {
    const id = setInterval(() => setRemaining(compute(deadline)), 1000);
    return () => clearInterval(id);
  }, [deadline]);

  const urgent = !remaining.expired && remaining.days < 1;
  const warning = !remaining.expired && remaining.days < 3;

  return (
    <div
      role="timer"
      aria-live="polite"
      className={cn(
        'flex items-center gap-3 rounded-lg border px-4 py-3',
        remaining.expired
          ? 'border-danger-200 bg-danger-50 text-danger-700'
          : urgent
          ? 'border-danger-200 bg-danger-50 text-danger-700'
          : warning
          ? 'border-warning-200 bg-warning-50 text-warning-700'
          : 'border-primary-100 bg-primary-50 text-primary-700',
        className,
      )}
    >
      <svg
        viewBox="0 0 20 20"
        fill="currentColor"
        className="h-5 w-5 shrink-0"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .2.08.39.22.53l3 3a.75.75 0 001.06-1.06L10.75 9.69V5z"
          clipRule="evenodd"
        />
      </svg>
      <div className="flex-1 text-sm">
        <p className="font-semibold">
          {remaining.expired ? `${label} has passed` : label}
        </p>
        {!remaining.expired && (
          <p className="mt-0.5 font-mono text-xs tabular-nums">
            {remaining.days}d · {String(remaining.hours).padStart(2, '0')}h ·{' '}
            {String(remaining.minutes).padStart(2, '0')}m ·{' '}
            {String(remaining.seconds).padStart(2, '0')}s remaining
          </p>
        )}
        <p className="mt-0.5 text-[11px] opacity-80">
          Due {new Date(deadline).toLocaleString()}
        </p>
      </div>
    </div>
  );
}
