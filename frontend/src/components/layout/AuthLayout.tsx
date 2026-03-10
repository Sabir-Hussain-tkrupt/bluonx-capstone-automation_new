import { Outlet } from 'react-router-dom';
import bluonxLogo from '@/assets/bluonx-logo.png';

export function AuthLayout() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <img src={bluonxLogo} alt="" className="mx-auto h-12 w-12" />
          <h1 className="mt-2 text-2xl font-bold text-primary-700">BluOnX</h1>
          <p className="text-xs text-gray-400">Bid Management System</p>
        </div>
        <Outlet />
      </div>
    </div>
  );
}
