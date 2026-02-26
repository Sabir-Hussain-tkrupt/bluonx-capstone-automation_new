import { useParams } from 'react-router-dom';

export function BidManagementPage() {
  const { id, taskId } = useParams<{ id: string; taskId: string }>();

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900">Bid Management</h1>
      <p className="mt-2 text-sm text-gray-500">Project ID: {id}</p>
      <p className="mt-1 text-sm text-gray-500">Task ID: {taskId}</p>
      <p className="mt-1 text-sm text-gray-400">Bid management will be built in Phase 4.</p>
    </div>
  );
}
