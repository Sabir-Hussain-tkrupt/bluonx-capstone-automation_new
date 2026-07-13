import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import { useMilestoneEvents } from '@/features/milestones/hooks/useMilestoneEvents';
import type { MilestoneEvent } from '@/features/milestones/api/milestone.queries';
import { formatMilestoneDate } from '../utils/formatDate';

function formatStatus(status: string | null): string {
  if (!status) return '—';
  return status.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function actorName(e: MilestoneEvent): string {
  if (e.trigger_type === 'vendor_response') return e.actor_vendor?.full_name ?? 'Vendor';
  if (e.trigger_type === 'system_no_response') return 'System';
  return e.actor?.full_name ?? 'Unknown';
}

/**
 * Builds the human line from trigger_type + from→to + a cycle bump. `older` is the
 * chronologically previous event (the newest-first list's next index), used to
 * detect a reschedule (its cycle_number increased). vendor_response /
 * system_no_response render generically — none exist until 10.2/10.3, but the
 * component is forward-compatible and must not stub them.
 */
function describe(e: MilestoneEvent, older: MilestoneEvent | undefined): string {
  const who = actorName(e);

  if (e.trigger_type === 'creation') return `Milestone created by ${who}`;

  if (e.trigger_type === 'pm_action') {
    if (e.to_status === 'in_progress') {
      const rescheduled =
        older != null &&
        e.cycle_number != null &&
        older.cycle_number != null &&
        e.cycle_number > older.cycle_number;
      if (rescheduled) {
        const end = e.working_end_date ? formatMilestoneDate(e.working_end_date) : 'a new date';
        return `Rescheduled: end date moved to ${end} by ${who}`;
      }
      return `Marked started by ${who}`;
    }
    if (e.to_status === 'completed') return `Marked completed by ${who}`;
    if (e.to_status === 'cancelled') return `Milestone cancelled by ${who}`;
  }

  // vendor_response / system_no_response / any unmapped pm target → generic.
  return `${formatStatus(e.from_status)} → ${formatStatus(e.to_status)} by ${who}`;
}

export function MilestoneActivityTimeline({ milestoneId }: { milestoneId: string }) {
  const { data: events, isLoading, error } = useMilestoneEvents(milestoneId);

  return (
    <Card>
      <div className="p-6">
        <h3 className="mb-4 text-sm font-semibold text-secondary-900">Activity</h3>

        {isLoading ? (
          <div className="space-y-3">
            <Skeleton height="20px" width="70%" />
            <Skeleton height="20px" width="55%" />
          </div>
        ) : error ? (
          <p className="text-sm text-danger-600">Could not load activity.</p>
        ) : !events || events.length === 0 ? (
          <p className="text-sm text-secondary-500">No activity recorded yet.</p>
        ) : (
          <ol className="relative space-y-5 border-l border-secondary-200 pl-5">
            {events.map((e, i) => (
              <li key={e.id} className="relative">
                <span
                  className="absolute top-1 -left-[1.4rem] h-2.5 w-2.5 rounded-full border-2 border-white bg-secondary-400"
                  aria-hidden="true"
                />
                <p className="text-sm font-medium text-secondary-900">
                  {describe(e, events[i + 1])}
                </p>
                <p className="mt-0.5 text-xs text-secondary-500">
                  {formatMilestoneDate(e.created_at.slice(0, 10))}
                </p>
                {e.note && <p className="mt-1 text-xs text-secondary-600">{e.note}</p>}
              </li>
            ))}
          </ol>
        )}
      </div>
    </Card>
  );
}
