import { describe, it, expect } from 'vitest';
import { buildMilestonePath } from '../buildMilestonePath';
import { ROUTES } from '@/constants/routes';

describe('buildMilestonePath', () => {
  it('fills the ROUTES.MILESTONE_DETAIL template with the three ids', () => {
    expect(buildMilestonePath('proj-1', 'task-2', 'ms-3')).toBe(
      '/projects/proj-1/tasks/task-2/milestones/ms-3',
    );
  });

  it('matches the ROUTES.MILESTONE_DETAIL template shape', () => {
    const path = buildMilestonePath('p', 't', 'm');
    const expected = ROUTES.MILESTONE_DETAIL.replace(':id', 'p')
      .replace(':taskId', 't')
      .replace(':milestoneId', 'm');
    expect(path).toBe(expected);
    // No unreplaced template segments remain.
    expect(path).not.toContain(':');
  });
});
