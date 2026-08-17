/**
 * fetchTaskAwardState — the single award-first read behind the task detail
 * contract section.
 *
 * What matters here is normalization. PostgREST returns a to-one embed as an
 * object and a to-many as an array, and which one you get depends on how it
 * detected the relationship (contracts.award_id is NOT NULL UNIQUE, so `contracts`
 * is to-one today). Both shapes are handled so a re-detection can't silently make
 * the section render nothing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const maybeSingle = vi.fn();
const notFn = vi.fn((_col: string, _op: string, _val: string) => ({ maybeSingle }));
const eq = vi.fn((_col: string, _val: string) => ({ not: notFn }));
const select = vi.fn((_cols: string) => ({ eq }));
const from = vi.fn((_table: string) => ({ select }));

// Indirected through an arrow so the factory does not touch `from` until the
// module under test is actually imported.
vi.mock('@/lib/supabase', () => ({
  supabase: { from: (table: string) => from(table) },
}));

import { fetchTaskAwardState } from '../milestone.queries';

const CONTRACT = {
  id: 'c-1',
  status: 'sent_for_signature',
  contract_number: 'CON-2026-ABCD1234',
  start_date: null,
  end_date: null,
};

beforeEach(() => vi.clearAllMocks());

describe('fetchTaskAwardState', () => {
  it('reads the active award only, mirroring idx_awards_one_active_per_task', async () => {
    maybeSingle.mockResolvedValue({ data: null, error: null });

    await fetchTaskAwardState('task-1');

    expect(from).toHaveBeenCalledWith('awards');
    expect(eq).toHaveBeenCalledWith('task_id', 'task-1');
    // Declined and cancelled awards free the task for re-award; offering to send
    // a contract there would push one the vendor already rejected.
    expect(notFn).toHaveBeenCalledWith(
      'status',
      'in',
      '("declined_by_vendor","cancelled")',
    );
  });

  it('returns null when the task has no active award', async () => {
    maybeSingle.mockResolvedValue({ data: null, error: null });
    expect(await fetchTaskAwardState('task-1')).toBeNull();
  });

  it('flattens object-shaped embeds and reports the envelope', async () => {
    maybeSingle.mockResolvedValue({
      data: {
        id: 'award-1',
        status: 'pending_acceptance',
        vendors: { company_name: 'Acme Grading LLC' },
        contracts: { ...CONTRACT, docusign_envelopes: [{ id: 'env-1' }] },
      },
      error: null,
    });

    expect(await fetchTaskAwardState('task-1')).toEqual({
      awardId: 'award-1',
      awardStatus: 'pending_acceptance',
      vendorCompanyName: 'Acme Grading LLC',
      contract: CONTRACT,
      hasEnvelope: true,
    });
  });

  it('flattens array-shaped embeds identically', async () => {
    maybeSingle.mockResolvedValue({
      data: {
        id: 'award-1',
        status: 'pending_acceptance',
        vendors: [{ company_name: 'Acme Grading LLC' }],
        contracts: [{ ...CONTRACT, docusign_envelopes: [{ id: 'env-1' }] }],
      },
      error: null,
    });

    const result = await fetchTaskAwardState('task-1');
    expect(result?.contract).toEqual(CONTRACT);
    expect(result?.vendorCompanyName).toBe('Acme Grading LLC');
    expect(result?.hasEnvelope).toBe(true);
  });

  it('reports no envelope when the send died before the contract row was written', async () => {
    maybeSingle.mockResolvedValue({
      data: {
        id: 'award-1',
        status: 'pending_acceptance',
        vendors: { company_name: 'Acme Grading LLC' },
        contracts: null,
      },
      error: null,
    });

    const result = await fetchTaskAwardState('task-1');
    // The award is still surfaced — that is the whole point. A contract-keyed read
    // returned nothing here and the failure was invisible.
    expect(result?.awardId).toBe('award-1');
    expect(result?.contract).toBeNull();
    expect(result?.hasEnvelope).toBe(false);
  });

  it('reports no envelope when the contract exists but nothing went out', async () => {
    maybeSingle.mockResolvedValue({
      data: {
        id: 'award-1',
        status: 'pending_acceptance',
        vendors: { company_name: 'Acme Grading LLC' },
        contracts: { ...CONTRACT, docusign_envelopes: [] },
      },
      error: null,
    });

    const result = await fetchTaskAwardState('task-1');
    expect(result?.contract).toEqual(CONTRACT);
    expect(result?.hasEnvelope).toBe(false);
  });

  it('treats a terminated contract as absent, as the contract-keyed read did', async () => {
    maybeSingle.mockResolvedValue({
      data: {
        id: 'award-1',
        status: 'pending_acceptance',
        vendors: { company_name: 'Acme Grading LLC' },
        contracts: {
          ...CONTRACT,
          status: 'terminated',
          docusign_envelopes: [{ id: 'env-1' }],
        },
      },
      error: null,
    });

    const result = await fetchTaskAwardState('task-1');
    // Keeps ContractPanel / MilestonesCard visibility unchanged from the old
    // .neq('status','terminated') filter.
    expect(result?.contract).toBeNull();
  });

  it('tolerates a missing vendor embed rather than throwing', async () => {
    maybeSingle.mockResolvedValue({
      data: {
        id: 'award-1',
        status: 'pending_acceptance',
        vendors: null,
        contracts: null,
      },
      error: null,
    });

    expect((await fetchTaskAwardState('task-1'))?.vendorCompanyName).toBeNull();
  });

  it('throws a converted ApiError on a read failure', async () => {
    maybeSingle.mockResolvedValue({
      data: null,
      error: { message: 'permission denied', code: '42501' },
    });

    await expect(fetchTaskAwardState('task-1')).rejects.toThrow(/permission denied/i);
  });
});
