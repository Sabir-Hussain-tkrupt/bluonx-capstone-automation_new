import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  compareBy,
  formatStalenessHint,
  getScoreBandVariant,
  maxScoredAt,
  parseDecimal,
} from './score-display';
import type { BidScoreRow, ScoringMetadata } from '@/features/bids/types';

function makeRow(opts: {
  id?: string;
  total?: string | null;
  thisTotal?: string | null;
  timeline?: number | null;
  scoredAt?: string | null;
}): BidScoreRow {
  // Use `in opts` to distinguish "omitted" from "null" — `??` would collapse
  // an explicit null to the default and silently hide null-sort tests.
  const total: string | null = 'total' in opts ? (opts.total ?? null) : '80.00';
  const thisTotal: string | null =
    'thisTotal' in opts ? (opts.thisTotal ?? null) : '100000.00';
  const timeline: number | null =
    'timeline' in opts ? (opts.timeline ?? null) : 80;
  const scoredAt: string | null =
    'scoredAt' in opts ? (opts.scoredAt ?? null) : '2026-07-02T12:00:00+00:00';

  const sub_scores = {
    price: 80,
    compliance: 80,
    performance: 75,
    capacity: 80,
    timeline: timeline ?? 80,
  };
  const metadata: ScoringMetadata = {
    rubric_version: 'v1.0',
    weights: { price: 0.5 },
    inputs: {
      this_total: thisTotal,
      lowest_valid_total: '100000.00',
      onboarding_status: 'complete',
      insurance_expiration: '2026-12-31',
      deadline: '2026-07-01',
      max_active_jobs: 5,
      current_active_jobs: 1,
      proposed_start_date: '2026-07-15',
      desired_start_date: '2026-07-15',
    },
    sub_scores,
    cohort_size: 3,
    computed_at: '2026-07-02T12:00:00+00:00',
  };
  return {
    id: opts.id ?? 'score-1',
    bid_submission_id: opts.id ?? 'sub-1',
    vendor_company_name: 'Acme',
    price_score: '80.00',
    compliance_score: '80.00',
    performance_score: '75.00',
    capacity_score: '80.00',
    timeline_score: String(sub_scores.timeline.toFixed(2)),
    total_weighted_score: total,
    scoring_metadata: metadata,
    scored_at: scoredAt,
    scored_by: null,
  };
}

describe('getScoreBandVariant', () => {
  it.each([
    [100, 'success'],
    [75, 'success'],
    [74.99, 'warning'],
    [50, 'warning'],
    [49.99, 'danger'],
    [0, 'danger'],
  ] as const)('score %s → %s', (input, expected) => {
    expect(getScoreBandVariant(input)).toBe(expected);
  });

  it('null → neutral', () => {
    expect(getScoreBandVariant(null)).toBe('neutral');
  });

  it('NaN → neutral', () => {
    expect(getScoreBandVariant(NaN)).toBe('neutral');
  });
});

describe('parseDecimal', () => {
  it('parses string decimals', () => {
    expect(parseDecimal('100000.50')).toBe(100000.5);
  });
  it('null / empty / NaN → null', () => {
    expect(parseDecimal(null)).toBeNull();
    expect(parseDecimal('')).toBeNull();
    expect(parseDecimal('abc')).toBeNull();
  });
});

describe('maxScoredAt', () => {
  it('empty list → null', () => {
    expect(maxScoredAt([])).toBeNull();
  });
  it('returns the latest ISO string', () => {
    const rows = [
      makeRow({ id: 'a', scoredAt: '2026-07-01T00:00:00+00:00' }),
      makeRow({ id: 'b', scoredAt: '2026-07-02T12:00:00+00:00' }),
      makeRow({ id: 'c', scoredAt: null }),
    ];
    expect(maxScoredAt(rows)).toBe('2026-07-02T12:00:00+00:00');
  });
});

describe('formatStalenessHint', () => {
  beforeEach(() => {
    // Anchor "now" so formatRelativeTime is deterministic.
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-02T12:05:00Z'));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('not stale when counts match and no newer submission', () => {
    const out = formatStalenessHint(
      '2026-07-02T12:00:00+00:00',
      '2026-07-02T11:00:00+00:00',
      3,
      3,
    );
    expect(out.isStale).toBe(false);
    expect(out.newBidsCount).toBe(0);
  });

  it('stale when valid_submission_count > cohort_size', () => {
    const out = formatStalenessHint(
      '2026-07-02T12:00:00+00:00',
      '2026-07-02T11:00:00+00:00',
      5,
      3,
    );
    expect(out.isStale).toBe(true);
    expect(out.newBidsCount).toBe(2);
  });

  it('stale when latest_submission_at > scored_at (count tied, revision case)', () => {
    const out = formatStalenessHint(
      '2026-07-02T10:00:00+00:00',
      '2026-07-02T11:00:00+00:00',
      3,
      3,
    );
    expect(out.isStale).toBe(true);
    expect(out.newBidsCount).toBe(1);   // visible even though count gap is 0
  });

  it('size gap takes precedence over timestamp signal', () => {
    const out = formatStalenessHint(
      '2026-07-02T10:00:00+00:00',
      '2026-07-02T11:00:00+00:00',
      5,
      3,
    );
    expect(out.newBidsCount).toBe(2);
  });

  it('scoredAt null → "—" label, but stale only if counts mismatch', () => {
    const out = formatStalenessHint(null, '2026-07-02T11:00:00+00:00', 1, 0);
    expect(out.scoredLabel).toBe('—');
    expect(out.isStale).toBe(true);
    expect(out.newBidsCount).toBe(1);
  });
});

describe('compareBy', () => {
  it("by 'total' desc — backend tie-break: total desc, then this_total asc, then id", () => {
    const a = makeRow({ id: 'aaa', total: '80.00', thisTotal: '100000.00' });
    const b = makeRow({ id: 'bbb', total: '80.00', thisTotal: '90000.00' });
    const c = makeRow({ id: 'ccc', total: '90.00', thisTotal: '100000.00' });
    const sorted = [a, b, c].sort(compareBy('total', 'desc'));
    expect(sorted.map((r) => r.bid_submission_id)).toEqual(['ccc', 'bbb', 'aaa']);
  });

  it("by 'price' asc sorts lowest-total first", () => {
    const a = makeRow({ id: 'a', thisTotal: '100000.00' });
    const b = makeRow({ id: 'b', thisTotal: '70000.00' });
    const sorted = [a, b].sort(compareBy('price', 'asc'));
    expect(sorted[0].bid_submission_id).toBe('b');
  });

  it("by 'timeline' desc sorts highest score first", () => {
    const a = makeRow({ id: 'a', timeline: 50 });
    const b = makeRow({ id: 'b', timeline: 100 });
    const sorted = [a, b].sort(compareBy('timeline', 'desc'));
    expect(sorted[0].bid_submission_id).toBe('b');
  });

  it('null values sort to the bottom regardless of direction', () => {
    const a = makeRow({ id: 'a', total: null });
    const b = makeRow({ id: 'b', total: '60.00' });
    const sortedDesc = [a, b].sort(compareBy('total', 'desc'));
    expect(sortedDesc[0].bid_submission_id).toBe('b');
    const sortedAsc = [a, b].sort(compareBy('total', 'asc'));
    expect(sortedAsc[0].bid_submission_id).toBe('b');
  });
});
