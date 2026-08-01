import { act } from 'react';
import { renderHook } from '@testing-library/react';
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { useTabParam } from '@/hooks/useTabParam';

const TABS = ['overview', 'tasks', 'documents'];

/** Renders the hook alongside the live location, so writes can be asserted. */
function renderAt(entry: string) {
  return renderHook(
    () => ({ tab: useTabParam(TABS), location: useLocation() }),
    {
      wrapper: ({ children }) => (
        <MemoryRouter initialEntries={[entry]}>{children}</MemoryRouter>
      ),
    },
  );
}

describe('useTabParam', () => {
  it('defaults to the first tab when the param is absent', () => {
    const { result } = renderAt('/projects/abc');
    expect(result.current.tab[0]).toBe('overview');
  });

  it('reads the active tab from the URL', () => {
    const { result } = renderAt('/projects/abc?tab=documents');
    expect(result.current.tab[0]).toBe('documents');
  });

  it('falls back to the first tab for an unrecognised value', () => {
    // A hand-typed or stale ?tab must not render an empty panel.
    const { result } = renderAt('/projects/abc?tab=milestones');
    expect(result.current.tab[0]).toBe('overview');
  });

  it('writes the param when a non-default tab is selected', () => {
    const { result } = renderAt('/projects/abc');

    act(() => result.current.tab[1]('tasks'));

    expect(result.current.tab[0]).toBe('tasks');
    expect(result.current.location.search).toBe('?tab=tasks');
  });

  it('drops the param when returning to the default tab', () => {
    const { result } = renderAt('/projects/abc?tab=tasks');

    act(() => result.current.tab[1]('overview'));

    expect(result.current.tab[0]).toBe('overview');
    expect(result.current.location.search).toBe('');
  });

  it('preserves unrelated query params', () => {
    const { result } = renderAt('/projects/abc?highlight=42');

    act(() => result.current.tab[1]('documents'));

    const params = new URLSearchParams(result.current.location.search);
    expect(params.get('highlight')).toBe('42');
    expect(params.get('tab')).toBe('documents');
  });

  it('replaces rather than pushes, so tab switching does not stack history', () => {
    // Otherwise backing out of a page you browsed takes one press per switch,
    // and Tabs activates on arrow keys, so it would be one per keypress.
    const { result } = renderHook(
      () => ({ tab: useTabParam(TABS), location: useLocation(), navigate: useNavigate() }),
      {
        wrapper: ({ children }) => (
          <MemoryRouter initialEntries={['/projects', '/projects/abc']} initialIndex={1}>
            {children}
          </MemoryRouter>
        ),
      },
    );

    act(() => result.current.tab[1]('tasks'));
    act(() => result.current.tab[1]('documents'));
    act(() => result.current.navigate(-1));

    // One press leaves the project. Were these pushes, it would land back on
    // '/projects/abc?tab=tasks' and take three presses to get out.
    expect(result.current.location.pathname).toBe('/projects');
  });
});
