import { useEffect, useState } from 'react';

interface CountdownState {
  remaining: string;
  isPassed: boolean;
  /**
   * Short label describing time elapsed since the deadline (e.g.,
   * `"passed 2d ago"`). `null` while the deadline is still in the
   * future.
   */
  passedLabel: string | null;
}

/**
 * Live countdown for a bid package deadline.
 *
 * - `remaining`: human label like `"3d 4h remaining"` while the deadline
 *   is in the future. Switches to `"Deadline passed"` once it elapses
 *   (kept identical to the prior detail-page behavior).
 * - `isPassed`: true once the deadline is in the past.
 * - `passedLabel`: only populated when `isPassed` — used by the list
 *   view to render "passed Nd ago" badges.
 */
export function useCountdown(deadline: string): CountdownState {
  const [remaining, setRemaining] = useState('');
  const [isPassed, setIsPassed] = useState(false);
  const [passedLabel, setPassedLabel] = useState<string | null>(null);

  useEffect(() => {
    const calc = () => {
      const diff = new Date(deadline).getTime() - Date.now();
      if (diff <= 0) {
        setRemaining('Deadline passed');
        setIsPassed(true);
        setPassedLabel(formatPassedLabel(-diff));
        return;
      }
      setIsPassed(false);
      setPassedLabel(null);
      const days = Math.floor(diff / (1000 * 60 * 60 * 24));
      const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      const parts: string[] = [];
      if (days > 0) parts.push(`${days}d`);
      if (hours > 0) parts.push(`${hours}h`);
      if (days === 0) parts.push(`${mins}m`);
      setRemaining(`${parts.join(' ')} remaining`);
    };
    calc();
    const interval = setInterval(calc, 60_000);
    return () => clearInterval(interval);
  }, [deadline]);

  return { remaining, isPassed, passedLabel };
}

function formatPassedLabel(elapsedMs: number): string {
  const days = Math.floor(elapsedMs / (1000 * 60 * 60 * 24));
  if (days >= 1) return `passed ${days}d ago`;
  const hours = Math.floor(elapsedMs / (1000 * 60 * 60));
  if (hours >= 1) return `passed ${hours}h ago`;
  const mins = Math.max(1, Math.floor(elapsedMs / (1000 * 60)));
  return `passed ${mins}m ago`;
}
