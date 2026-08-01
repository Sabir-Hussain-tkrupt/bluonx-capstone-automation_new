import { useParams } from 'react-router-dom';
import { useProject } from '@/features/projects/hooks/useProject';
import { TaskList } from '@/features/tasks/components/TaskList';
import { Skeleton } from '@/components/ui/Skeleton';
import { Alert } from '@/components/ui/Alert';

export function TaskListPage() {
  const { id } = useParams<{ id: string }>();
  const { data: project, isLoading, error } = useProject(id!);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton height="32px" width="50%" />
        <Skeleton height="300px" />
      </div>
    );
  }

  if (error || !project) {
    return (
      <Alert variant="danger" title="Project not found">
        The project you are looking for does not exist or has been deleted.
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-secondary-900 sm:text-2xl">
        Tasks: {project.name}
      </h1>
      <TaskList projectId={id!} projectBudget={project.budget} />
    </div>
  );
}
