/** Human label for a paused duration, e.g. "stalled 12 days" / "stalled today". */
export function formatStalled(daysPaused: number | null): string {
  if (daysPaused == null) return '';
  if (daysPaused <= 0) return 'stalled today';
  return `stalled ${daysPaused} ${daysPaused === 1 ? 'day' : 'days'}`;
}
