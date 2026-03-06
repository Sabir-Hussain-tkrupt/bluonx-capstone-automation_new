import { Outlet } from 'react-router-dom';

export function AuthLayout() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50">
      <div className="w-full max-w-md p-6">
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-bold text-primary-700">BluOnX</h1>
          <p className="text-xs text-gray-400">Bid Management System</p>
        </div>
        <Outlet />
      </div>
    </div>
  );
}
