import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({ api: { get: vi.fn() } }));

import { api } from '@/lib/api';
import { fetchTasks } from '../task.queries';

const mockGet = vi.mocked(api.get);

function response(items: unknown[]) {
  return { data: { items, total: items.length, page: 1, page_size: 50 } };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockResolvedValue(response([]));
});

describe('fetchTasks', () => {
  it('calls the project-scoped tasks endpoint with mapped params', async () => {
    await fetchTasks({ projectId: 'p1', search: 'grad', status: 'draft', page: 2, sort_by: 'name', sort_dir: 'desc' });

    expect(mockGet).toHaveBeenCalledWith(
      '/projects/p1/tasks',
      expect.objectContaining({
        params: expect.objectContaining({ search: 'grad', status: 'draft', page: 2, sort_by: 'name', sort_dir: 'desc' }),
      }),
    );
  });

  it('normalizes a string budget_estimate to a number', async () => {
    mockGet.mockResolvedValue(response([{ id: 't1', name: 'Grading', budget_estimate: '5000.50' }]));

    const result = await fetchTasks({ projectId: 'p1' });
    const row = result.items[0];

    expect(row.budget_estimate).toBe(5000.5);
    expect(typeof row.budget_estimate).toBe('number');
  });

  it('leaves a null budget_estimate as null', async () => {
    mockGet.mockResolvedValue(response([{ id: 't1', name: 'Grading', budget_estimate: null }]));

    const result = await fetchTasks({ projectId: 'p1' });
    expect(result.items[0].budget_estimate).toBeNull();
  });
});
