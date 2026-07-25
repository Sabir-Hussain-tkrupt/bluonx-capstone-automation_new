import { createRef } from 'react';

/**
 * The dashboard's main scroll container. DashboardLayout attaches the element
 * here on mount and React clears it on unmount, so a null ref means we are on a
 * route outside the dashboard (login, vendor portal) where the window scrolls.
 *
 * A module-level ref rather than context: ScrollToTop mounts outside the route
 * tree, so it and DashboardLayout share no provider short of App itself.
 */
export const mainScrollRef = createRef<HTMLDivElement>();
