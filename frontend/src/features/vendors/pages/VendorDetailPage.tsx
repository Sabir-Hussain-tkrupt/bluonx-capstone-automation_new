import { useParams } from 'react-router-dom';

export function VendorDetailPage() {
  const { id } = useParams<{ id: string }>();

  return (
    <div>
      <h1 className="text-2xl font-semibold text-gray-900">Vendor Detail</h1>
      <p className="mt-2 text-sm text-gray-500">Vendor ID: {id}</p>
      <p className="mt-1 text-sm text-gray-400">Vendor detail page will be built in Phase 3 (Task 3.1).</p>
    </div>
  );
}
