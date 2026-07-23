import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }));

import { api } from '@/lib/api';
import { fetchProjects } from '../project.queries';

const mockGet = vi.mocked(api.get);

function response(items: unknown[]) {
  return { data: { items, total: items.length, page: 1, page_size: 25 } };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockResolvedValue(response([]));
});

describe('fetchProjects param mapping', () => {
  it('sends status and no archived_only for a normal list', async () => {
    await fetchProjects({ search: 'grad', status: 'active', page: 2, page_size: 25, sort_by: 'name', sort_dir: 'asc' });

    expect(mockGet).toHaveBeenCalledWith(
      '/projects',
      expect.objectContaining({
        params: expect.objectContaining({
          search: 'grad',
          status: 'active',
          archived_only: undefined,
          page: 2,
        }),
      }),
    );
  });

  it('asks for archived_only and drops the status filter in the archived view', async () => {
    await fetchProjects({ archived: true, status: 'active' });

    const params = mockGet.mock.calls[0][1]!.params;
    expect(params.archived_only).toBe(true);
    expect(params.status).toBeUndefined();
  });
});

describe('fetchProjects numeric normalization', () => {
  it('coerces string budget/latitude/longitude to numbers', async () => {
    mockGet.mockResolvedValue(
      response([
        {
          id: 'p1',
          name: 'Riverside',
          budget: '1500000.50',
          latitude: '38.62',
          longitude: '-90.19',
        },
      ]),
    );

    const result = await fetchProjects();
    const row = result.items[0];

    expect(row.budget).toBe(1500000.5);
    expect(typeof row.budget).toBe('number');
    expect(row.latitude).toBe(38.62);
    expect(row.longitude).toBe(-90.19);
  });

  it('leaves a null budget as null', async () => {
    mockGet.mockResolvedValue(response([{ id: 'p1', name: 'Riverside', budget: null }]));

    const result = await fetchProjects();
    expect(result.items[0].budget).toBeNull();
  });
});
