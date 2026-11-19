import type { TradeUsage } from '../types';

const LABELS: [keyof TradeUsage, string, string][] = [
  ['tasks', 'task', 'tasks'],
  ['vendors', 'vendor', 'vendors'],
  ['task_templates', 'task template', 'task templates'],
  ['bid_templates', 'bid template', 'bid templates'],
  ['budget_template_lines', 'budget template line', 'budget template lines'],
  ['variances', 'variance', 'variances'],
  ['subtrades', 'subtrade', 'subtrades'],
];

/** "3 tasks, 1 vendor and 2 subtrades". */
export function describeTradeUsage(usage: TradeUsage, opts: { excludeSubtrades?: boolean } = {}): string {
  const parts = LABELS.filter(([key]) => !(opts.excludeSubtrades && key === 'subtrades'))
    .map(([key, one, many]) => {
      const n = Number(usage[key]) || 0;
      return n > 0 ? `${n} ${n === 1 ? one : many}` : null;
    })
    .filter((p): p is string => p !== null);
  if (parts.length <= 1) return parts[0] ?? 'nothing';
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}
