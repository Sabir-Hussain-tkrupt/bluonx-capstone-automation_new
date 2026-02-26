import { useParams } from 'react-router-dom';

export function TaskListPage() {
  const { id } = useParams<{ id: string }>();

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900">Tasks</h1>
      <p className="mt-2 text-sm text-gray-500">Project ID: {id}</p>
      <p className="mt-1 text-sm text-gray-400">Task list will be built in Phase 3 (Task 3.3).</p>
    </div>
  );
}
