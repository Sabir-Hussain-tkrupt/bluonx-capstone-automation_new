import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { queryKeys } from '@/lib/queryKeys';

const mockUseAuth = vi.fn();
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

import { useBreadcrumbs } from '@/hooks/useBreadcrumbs';

const PROJECT = '11111111-1111-4111-8111-111111111111';
const TASK = '22222222-2222-4222-8222-222222222222';
const PKG = '33333333-3333-4333-8333-333333333333';

function renderAt(path: string, seed?: (qc: QueryClient) => void) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  seed?.(queryClient);

  return renderHook(() => useBreadcrumbs(), {
    wrapper: ({ children }) => (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter>
      </QueryClientProvider>
    ),
  });
}

describe('useBreadcrumbs', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue({ profile: { role: 'admin' } });
  });

  it('labels entity crumbs from cached data', () => {
    const { result } = renderAt(`/projects/${PROJECT}/tasks/${TASK}`, (qc) => {
      qc.setQueryData(queryKeys.projects.detail(PROJECT), { name: 'Riverside Grading' });
      qc.setQueryData(queryKeys.tasks.detail(TASK), { name: 'Rough Grading' });
    });

    expect(result.current).toEqual([
      { label: 'Dashboard', href: '/dashboard' },
      { label: 'Projects', href: '/projects' },
      { label: 'Riverside Grading', href: `/projects/${PROJECT}?tab=tasks` },
      { label: 'Rough Grading', href: undefined },
    ]);
  });

  it('falls back to a neutral entity noun on a cache miss, never "Details"', () => {
    // The deep-link case: a hard refresh on a task URL, nothing in cache yet.
    const { result } = renderAt(`/projects/${PROJECT}/tasks/${TASK}`);

    expect(result.current.map((c) => c.label)).toEqual([
      'Dashboard',
      'Projects',
      'Project',
      'Task',
    ]);
  });

  it('renders a bid package crumb as its round number', () => {
    const { result } = renderAt(
      `/projects/${PROJECT}/tasks/${TASK}/bid-packages/${PKG}`,
      (qc) => qc.setQueryData(queryKeys.bidPackages.detail(PKG), { round_number: 2 }),
    );

    expect(result.current.at(-1)).toEqual({ label: 'Round 2', href: undefined });
  });

  it('never issues a fetch of its own', () => {
    // Breadcrumbs read the cache the page itself fills. If this hook could
    // fetch, every route change would fan out a wave of duplicate requests.
    // A default queryFn stands in for the real one: skipToken must win over it.
    const fetchSpy = vi.fn();
    const { result } = renderAt(`/projects/${PROJECT}`, (qc) =>
      qc.setQueryDefaults(queryKeys.projects.detail(PROJECT), { queryFn: fetchSpy }),
    );

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.current.at(-1)?.label).toBe('Project');
  });

  it('builds the calendar trail under Settings', () => {
    const { result } = renderAt('/settings/calendar');

    expect(result.current).toEqual([
      { label: 'Dashboard', href: '/dashboard' },
      { label: 'Settings', href: '/settings' },
      { label: 'Holiday Calendar', href: undefined },
    ]);
  });

  it('returns nothing for a route outside the dashboard layout', () => {
    expect(renderAt('/login').result.current).toEqual([]);
  });
});
