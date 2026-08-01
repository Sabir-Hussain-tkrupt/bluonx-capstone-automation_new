import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * Keeps a tabbed page's active tab in the URL (`?tab=documents`).
 *
 * Tabs whose panels hold distinct content, each with its own data, are
 * navigation rather than a view control, so they belong in the URL. Holding
 * them in `useState` means the back button cannot restore them (React Router
 * unmounts the page, so returning remounts it at the first tab), a refresh
 * loses your place, and no tab can be linked or bookmarked.
 *
 * Drop-in for `useState`: returns the same [value, setter] pair.
 *
 * Two behaviours worth knowing:
 * - The first tab is the default and carries NO param, so the common URL stays
 *   clean and pre-existing links keep working. An absent or unrecognised value
 *   resolves to it, so a hand-typed `?tab=garbage` cannot render a blank panel.
 * - Writes use `replace`, so switching tabs rewrites the current history entry
 *   instead of stacking one per switch. Backing out of a page you browsed is
 *   then a single press, and the entry left behind when you click into a child
 *   already carries the tab, which is what makes the back button restore it.
 *   Tabs activates on arrow keys, so pushing would add an entry per keypress.
 */
export function useTabParam(
  tabIds: readonly string[],
  param = 'tab',
): [string, (tabId: string) => void] {
  const [searchParams, setSearchParams] = useSearchParams();

  const requested = searchParams.get(param);
  const activeTab = requested && tabIds.includes(requested) ? requested : tabIds[0];

  const setActiveTab = useCallback(
    (tabId: string) => {
      setSearchParams(
        (current) => {
          // Copy rather than mutate, so unrelated query keys survive.
          const next = new URLSearchParams(current);
          if (tabId === tabIds[0]) next.delete(param);
          else next.set(param, tabId);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams, tabIds, param],
  );

  return [activeTab, setActiveTab];
}
