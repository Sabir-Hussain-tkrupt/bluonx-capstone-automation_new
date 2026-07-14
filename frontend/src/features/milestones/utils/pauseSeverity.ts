/**
 * Staleness of a paused milestone, keyed off `days_paused` from
 * `v_milestone_overview`. A number alone does not convey urgency, so the
 * attention surfaces escalate color: neutral < 7, amber >= 7, red >= 14.
 */
export type PauseSeverity = 'none' | 'neutral' | 'amber' | 'red';

export function pauseSeverity(daysPaused: number | null): PauseSeverity {
  if (daysPaused == null) return 'none';
  if (daysPaused >= 14) return 'red';
  if (daysPaused >= 7) return 'amber';
  return 'neutral';
}

/** Human label for a paused duration, e.g. "stalled 12 days" / "stalled today". */
export function formatStalled(daysPaused: number | null): string {
  if (daysPaused == null) return '';
  if (daysPaused <= 0) return 'stalled today';
  return `stalled ${daysPaused} ${daysPaused === 1 ? 'day' : 'days'}`;
}
