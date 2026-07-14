import { ROUTES } from '@/constants/routes';

/**
 * Build the milestone detail path from the single ROUTES template, so the route
 * is constructed in exactly one place. The template requires all three ids:
 * `/projects/:id/tasks/:taskId/milestones/:milestoneId`.
 */
export function buildMilestonePath(
  projectId: string,
  taskId: string,
  milestoneId: string,
): string {
  return ROUTES.MILESTONE_DETAIL.replace(':id', projectId)
    .replace(':taskId', taskId)
    .replace(':milestoneId', milestoneId);
}
