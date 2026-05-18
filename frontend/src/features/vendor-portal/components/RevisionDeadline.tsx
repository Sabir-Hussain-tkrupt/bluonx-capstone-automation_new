import { useEffect, useState } from 'react';

const DAY_MS = 24 * 60 * 60 * 1000;

interface RevisionDeadlineProps {
  /** ISO 8601 timestamptz string. */
  deadline: string;
}

function formatAbsolute(d: Date): string {
  // "Saturday, May 23 at 5:00 PM" — vendor's local timezone.
  const date = d.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  });
  const time = d.toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
  return `${date} at ${time}`;
}

/**
 * Revision deadline display. Within 24h it shows a prominent live
 * countdown (refreshed each minute); otherwise a relative date.
 * Native Date only — the SPA has no date library.
 */
export function RevisionDeadline({ deadline }: RevisionDeadlineProps) {
  const target = new Date(deadline).getTime();
  const [now, setNow] = useState(() => Date.now());

  const msLeft = target - now;
  const isSoon = msLeft > 0 && msLeft < DAY_MS;

  useEffect(() => {
    if (!isSoon) return;
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, [isSoon]);

  if (msLeft <= 0) {
    return (
      <p className="text-sm font-semibold text-danger-600">
        The revision deadline has passed.
      </p>
    );
  }

  if (isSoon) {
    const totalMinutes = Math.floor(msLeft / 60_000);
    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return (
      <div className="rounded-lg border border-warning-300 bg-warning-50 px-4 py-3 text-center">
        <p className="text-xs font-medium tracking-wide text-warning-700 uppercase">
          Revision due in
        </p>
        <p className="mt-1 text-2xl font-bold text-warning-800 tabular-nums">
          {hours}h {minutes}m
        </p>
      </div>
    );
  }

  return (
    <p className="text-sm text-secondary-700">
      Due <span className="font-semibold">{formatAbsolute(new Date(target))}</span>
    </p>
  );
}
