import { Link } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';

export function UnauthorizedPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50">
      <h1 className="text-6xl font-bold text-gray-300">403</h1>
      <p className="mt-4 text-lg text-gray-600">
        You don&apos;t have permission to access this page
      </p>
      <Link
        to={ROUTES.DASHBOARD}
        className="mt-6 text-blue-600 underline hover:text-blue-800"
      >
        Go to Dashboard
      </Link>
    </div>
  );
}
