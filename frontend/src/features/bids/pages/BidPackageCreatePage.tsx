import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { Alert } from '@/components/ui/Alert';
import { Skeleton } from '@/components/ui/Skeleton';
import { useTask } from '@/features/tasks/hooks/useTask';
import { BidPackageWizard } from '@/features/bids/components/BidPackageWizard/BidPackageWizard';

export function BidPackageCreatePage() {
  const { id: projectId, taskId } = useParams<{ id: string; taskId: string }>();
  const navigate = useNavigate();
  const { data: task, isLoading, error } = useTask(projectId!, taskId!);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton height="32px" width="50%" />
        <Skeleton height="400px" />
      </div>
    );
  }

  if (error || !task) {
    return (
      <Alert variant="danger" title="Task not found">
        The task you are looking for does not exist or has been deleted.
      </Alert>
    );
  }

  if (task.bid_type !== 'competitive') {
    return (
      <Alert variant="warning" title="Not eligible">
        Only competitive bid tasks can create bid packages.
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => navigate(`/projects/${projectId}/tasks/${taskId}`)}
          className="shrink-0 rounded-lg p-1 text-secondary-400 hover:bg-secondary-100 hover:text-secondary-600"
        >
          <ArrowLeft className="h-5 w-5" aria-hidden="true" />
        </button>
        <div>
          <h1 className="text-xl font-semibold text-secondary-900 sm:text-2xl">
            Create Bid Package
          </h1>
          <p className="mt-0.5 text-sm text-secondary-500">{task.name}</p>
        </div>
      </div>

      <BidPackageWizard projectId={projectId!} taskId={taskId!} task={task} />
    </div>
  );
}
