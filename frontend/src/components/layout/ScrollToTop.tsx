import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { mainScrollRef } from '@/components/layout/mainScrollRef';

/**
 * Scrolls to top of page on every route navigation.
 * Place inside <BrowserRouter> as a sibling of the main app tree.
 */
export function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    if (mainScrollRef.current) {
      mainScrollRef.current.scrollTo(0, 0);
    } else {
      window.scrollTo(0, 0);
    }
  }, [pathname]);

  return null;
}
