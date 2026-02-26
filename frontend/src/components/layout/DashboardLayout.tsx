import { Outlet } from 'react-router-dom';

export function DashboardLayout() {
  return (
    <div className="flex min-h-screen">
      {/* Sidebar placeholder — built in Task 2.8 */}
      <aside className="hidden w-64 border-r border-gray-200 bg-white lg:block">
        <div className="p-4">
          <p className="text-sm font-semibold text-gray-700">BluOnX</p>
          <p className="mt-1 text-xs text-gray-400">Sidebar built in Task 2.8</p>
        </div>
      </aside>

      {/* Main content area */}
      <main className="flex-1 bg-gray-50">
        {/* Top header placeholder — built in Task 2.8 */}
        <header className="border-b border-gray-200 bg-white px-6 py-4">
          <p className="text-sm text-gray-400">Header built in Task 2.8</p>
        </header>

        {/* Page content rendered by child routes */}
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
