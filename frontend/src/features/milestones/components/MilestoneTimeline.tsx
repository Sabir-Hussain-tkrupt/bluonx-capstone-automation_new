import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { useProjectTimeline } from '@/features/milestones/hooks/useProjectTimeline';
import { buildMilestonePath } from '@/features/milestones/utils/buildMilestonePath';
import { formatMilestoneDate } from '@/features/milestones/utils/formatDate';
import type { MilestoneOverviewRow } from '@/features/milestones/api/milestoneOverview.queries';
import type { MilestoneStatus } from '@/features/milestones/api/milestone.queries';

/** Bar fill per status, mirroring the StatusBadge palette. */
const STATUS_BAR_COLOR: Record<MilestoneStatus, string> = {
  scheduled: 'bg-secondary-400',
  in_progress: 'bg-info-500',
  delayed: 'bg-warning-500',
  unresponsive: 'bg-danger-500',
  completed: 'bg-success-500',
  cancelled: 'bg-secondary-300',
};

/** Parse a 'YYYY-MM-DD' date to a local-midnight epoch (matches formatMilestoneDate, TZ-safe). */
function toMs(value: string | null): number | null {
  if (!value) return null;
  const [y, m, d] = value.split('-').map(Number);
  if (!y || !m || !d) return null;
  return new Date(y, m - 1, d).getTime();
}

interface TaskGroup {
  taskId: string;
  taskName: string;
  rows: MilestoneOverviewRow[];
}

function groupByTask(rows: MilestoneOverviewRow[]): TaskGroup[] {
  const groups: TaskGroup[] = [];
  for (const row of rows) {
    const last = groups[groups.length - 1];
    if (last && last.taskId === row.task_id) {
      last.rows.push(row);
    } else {
      groups.push({ taskId: row.task_id, taskName: row.task_name, rows: [row] });
    }
  }
  return groups;
}

function TimelineBar({
  row,
  min,
  span,
  onClick,
}: {
  row: MilestoneOverviewRow;
  min: number;
  span: number;
  onClick: () => void;
}) {
  const startMs = toMs(row.start_date) ?? min;
  const endMs = toMs(row.end_date) ?? startMs;
  const baselineMs = toMs(row.baseline_end_date);

  const pct = (ms: number) => ((ms - min) / span) * 100;
  const left = Math.max(0, Math.min(100, pct(startMs)));
  const rawWidth = pct(endMs) - pct(startMs);
  const width = Math.max(rawWidth, 1.5); // keep zero-length bars visible

  const barColor = STATUS_BAR_COLOR[row.status] ?? 'bg-secondary-400';
  const baselineLeft = baselineMs != null ? Math.max(0, Math.min(100, pct(baselineMs))) : null;

  return (
    <button
      type="button"
      onClick={onClick}
      className="relative block h-6 w-full rounded hover:bg-secondary-50"
      title={`${row.milestone_name}: ${formatMilestoneDate(row.start_date)} to ${formatMilestoneDate(row.end_date)}`}
    >
      {/* Drift band + committed (baseline) marker, only when the end date moved. */}
      {row.end_date_moved && baselineLeft != null && (
        <>
          <span
            className="absolute top-1/2 h-3 -translate-y-1/2 rounded-sm bg-secondary-200/70"
            style={{
              left: `${Math.min(left + width, baselineLeft)}%`,
              width: `${Math.abs(baselineLeft - (left + width))}%`,
            }}
            aria-hidden="true"
          />
          <span
            className="absolute top-0 h-full border-l-2 border-dashed border-secondary-400"
            style={{ left: `${baselineLeft}%` }}
            title={`Committed end ${formatMilestoneDate(row.baseline_end_date)}`}
            aria-label={`Committed end ${formatMilestoneDate(row.baseline_end_date)}`}
          />
        </>
      )}
      {/* Working bar: start to current end, filled in the status color. */}
      <span
        className={`absolute top-1/2 h-4 -translate-y-1/2 rounded ${barColor}`}
        style={{ left: `${left}%`, width: `${width}%` }}
        aria-hidden="true"
      />
    </button>
  );
}

/**
 * Read-only project Gantt: one bar per milestone, grouped by task, over a shared
 * date axis with a "today" marker. When a milestone's end date has slipped from
 * its committed baseline, the baseline shows as a distinct dashed marker so the
 * drift is visible at a glance. Plain CSS (no chart dependency).
 */
export function MilestoneTimeline({ projectId }: { projectId: string }) {
  const navigate = useNavigate();
  const { data: rows = [], isLoading } = useProjectTimeline(projectId);

  const axis = useMemo(() => {
    const times: number[] = [];
    for (const r of rows) {
      for (const v of [r.start_date, r.end_date, r.baseline_end_date]) {
        const ms = toMs(v);
        if (ms != null) times.push(ms);
      }
    }
    const todayMs = toMs(new Date().toLocaleDateString('en-CA')); // 'YYYY-MM-DD' local
    if (todayMs != null) times.push(todayMs);

    if (times.length === 0) {
      return { min: 0, span: 1, todayMs: null as number | null };
    }
    const min = Math.min(...times);
    const max = Math.max(...times);
    // Guard divide-by-zero when a single milestone / all-equal dates collapse the span.
    const span = Math.max(max - min, 1);
    return { min, span, todayMs };
  }, [rows]);

  const groups = useMemo(() => groupByTask(rows), [rows]);

  const todayPct =
    axis.todayMs != null
      ? Math.max(0, Math.min(100, ((axis.todayMs - axis.min) / axis.span) * 100))
      : null;

  const axisMax = axis.min + axis.span;

  if (isLoading) {
    return (
      <div className="space-y-3 rounded-lg border border-secondary-200 bg-white p-6">
        <Skeleton height="24px" />
        <Skeleton height="24px" />
        <Skeleton height="24px" />
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-secondary-200 bg-white">
        <EmptyState
          title="No milestones yet"
          description="Milestones appear here once this project's tasks are awarded and contracted."
        />
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-secondary-200 bg-white p-4 sm:p-6">
      {/* Date axis header */}
      <div className="mb-3 flex items-center gap-4 border-b border-secondary-100 pb-2 text-xs text-secondary-500">
        <div className="w-40 shrink-0" />
        <div className="relative flex-1">
          <span className="absolute left-0">{formatMilestoneDate(new Date(axis.min).toLocaleDateString('en-CA'))}</span>
          <span className="absolute right-0">{formatMilestoneDate(new Date(axisMax).toLocaleDateString('en-CA'))}</span>
        </div>
      </div>

      <div className="space-y-5">
        {groups.map((group) => (
          <div key={group.taskId}>
            <p className="mb-1.5 truncate text-xs font-semibold uppercase tracking-wider text-secondary-500">
              {group.taskName}
            </p>
            <div className="space-y-1.5">
              {group.rows.map((row) => (
                <div key={row.milestone_id} className="flex items-center gap-4">
                  <div className="w-40 shrink-0 truncate text-sm text-secondary-900" title={row.milestone_name}>
                    {row.milestone_name}
                  </div>
                  <div className="relative flex-1">
                    {/* Today marker */}
                    {todayPct != null && (
                      <span
                        className="pointer-events-none absolute top-0 z-10 h-full border-l border-primary-500"
                        style={{ left: `${todayPct}%` }}
                        aria-hidden="true"
                      />
                    )}
                    <TimelineBar
                      row={row}
                      min={axis.min}
                      span={axis.span}
                      onClick={() =>
                        navigate(buildMilestonePath(row.project_id, row.task_id, row.milestone_id))
                      }
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-secondary-100 pt-3 text-xs text-secondary-500">
        <span className="flex items-center gap-1.5">
          <span className="h-0 w-4 border-t border-primary-500" /> Today
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-4 border-l-2 border-dashed border-secondary-400" /> Committed end (drift)
        </span>
      </div>
    </div>
  );
}
