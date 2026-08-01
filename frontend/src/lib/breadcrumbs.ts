import { generatePath, matchPath } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';

/**
 * Route-driven breadcrumb configuration.
 *
 * Crumbs are a property of the ROUTE, not of the URL string. The previous
 * implementation split the pathname and looked each segment up in a dictionary,
 * which meant (a) any segment missing from the dictionary leaked its raw slug,
 * and (b) every intermediate crumb got an href of the accumulated path whether
 * or not a route existed there — `.../tasks/:taskId/bid-packages` and
 * `.../tasks/:taskId/milestones` are URL namespaces with no page behind them,
 * so those crumbs linked straight to the 404 catch-all.
 *
 * Here each route names its parent explicitly, so a URL segment that is not a
 * destination simply never becomes a crumb, and the trail can differ from the
 * URL nesting where the two disagree.
 */

/** Entity whose display name is read from the React Query cache at render time. */
export type EntityKind =
  | 'project'
  | 'task'
  | 'vendor'
  | 'milestone'
  | 'bidPackage'
  | 'bidTemplate';

/** A label to be read from cached entity data, with a fallback for a cache miss. */
export interface EntityLabel {
  entity: EntityKind;
  /** Route param holding the entity id (e.g. 'taskId'). */
  param: string;
  /** Rendered when the entity is not in cache. Never a bare "Details". */
  fallback: string;
}

/** An EntityLabel with its id filled in from the matched route params. */
export interface ResolvedEntityLabel {
  entity: EntityKind;
  id: string;
  fallback: string;
}

interface CrumbConfig {
  /**
   * Parent route pattern. A function receives the viewer's role so a route can
   * skip a parent it is not allowed to visit.
   */
  parent?: string | ((ctx: TrailContext) => string | undefined);
  label: string | EntityLabel;
  /**
   * Query string identifying the tab of the parent page that contains this
   * route, e.g. '?tab=tasks'. Appended to the PARENT's crumb href, so clicking
   * up from a child lands on the tab you came from instead of the parent's
   * default tab, which is what the browser back button already does.
   */
  parentQuery?: string;
}

export interface TrailContext {
  isAdmin: boolean;
}

export interface CrumbDescriptor {
  label: string | ResolvedEntityLabel;
  /** Absolute path, or undefined for the current page (the last crumb). */
  href?: string;
}

/**
 * Every route rendered inside DashboardLayout. Routes outside it (auth, the
 * vendor portal, /unauthorized, /dev/components, the 404 catch-all) render no
 * breadcrumb at all and are intentionally absent — see EXCLUDED_ROUTES in the
 * test, which pins that list so a new route cannot quietly go unconfigured.
 */
export const CRUMB_CONFIG: Record<string, CrumbConfig> = {
  [ROUTES.DASHBOARD]: { label: 'Dashboard' },

  [ROUTES.VENDORS]: { parent: ROUTES.DASHBOARD, label: 'Vendors' },
  [ROUTES.VENDOR_DETAIL]: {
    parent: ROUTES.VENDORS,
    label: { entity: 'vendor', param: 'id', fallback: 'Vendor' },
  },

  [ROUTES.PROJECTS]: { parent: ROUTES.DASHBOARD, label: 'Projects' },
  [ROUTES.PROJECT_DETAIL]: {
    parent: ROUTES.PROJECTS,
    label: { entity: 'project', param: 'id', fallback: 'Project' },
  },
  [ROUTES.TASKS]: {
    parent: ROUTES.PROJECT_DETAIL,
    label: 'Tasks',
    parentQuery: '?tab=tasks',
  },

  // Parents to the project, NOT to /projects/:id/tasks: that page renders the
  // same TaskList as the project page's Tasks tab, so it is a rung to nowhere
  // new and only pads the trail.
  [ROUTES.TASK_DETAIL]: {
    parent: ROUTES.PROJECT_DETAIL,
    label: { entity: 'task', param: 'taskId', fallback: 'Task' },
    parentQuery: '?tab=tasks',
  },

  [ROUTES.CREATE_BID_PACKAGE]: { parent: ROUTES.TASK_DETAIL, label: 'New Bid Package' },
  [ROUTES.BID_PACKAGE_DETAIL]: {
    parent: ROUTES.TASK_DETAIL,
    label: { entity: 'bidPackage', param: 'bidPackageId', fallback: 'Bid Package' },
  },
  [ROUTES.BID_PACKAGE_COMPARE]: { parent: ROUTES.BID_PACKAGE_DETAIL, label: 'Compare' },

  [ROUTES.MILESTONE_DETAIL]: {
    parent: ROUTES.TASK_DETAIL,
    label: { entity: 'milestone', param: 'milestoneId', fallback: 'Milestone' },
  },
  [ROUTES.MILESTONES]: { parent: ROUTES.DASHBOARD, label: 'Milestones' },

  [ROUTES.BID_PACKAGES]: { parent: ROUTES.DASHBOARD, label: 'Bid Packages' },

  [ROUTES.BID_TEMPLATES]: { parent: ROUTES.DASHBOARD, label: 'Bid Templates' },
  [ROUTES.BID_TEMPLATE_NEW]: { parent: ROUTES.BID_TEMPLATES, label: 'New Template' },
  [ROUTES.BID_TEMPLATE_DETAIL]: {
    parent: ROUTES.BID_TEMPLATES,
    label: { entity: 'bidTemplate', param: 'id', fallback: 'Template' },
  },
  [ROUTES.BID_TEMPLATE_EDIT]: { parent: ROUTES.BID_TEMPLATE_DETAIL, label: 'Edit' },

  [ROUTES.NOTIFICATIONS]: { parent: ROUTES.DASHBOARD, label: 'Notifications' },

  [ROUTES.SETTINGS]: { parent: ROUTES.DASHBOARD, label: 'Settings' },
  [ROUTES.SETTINGS_TRADES]: { parent: ROUTES.SETTINGS, label: 'Trades' },
  [ROUTES.SETTINGS_USERS]: { parent: ROUTES.SETTINGS, label: 'Users' },
  // The calendar is the one /settings child open to non-admins, so for a PM its
  // parent crumb would link to an admin-gated route that bounces them to the
  // dashboard. Skip the rung instead of shipping a dead end.
  [ROUTES.SETTINGS_CALENDAR]: {
    parent: (ctx) => (ctx.isAdmin ? ROUTES.SETTINGS : ROUTES.DASHBOARD),
    label: 'Holiday Calendar',
  },
};

/**
 * Patterns ordered most-specific-first.
 *
 * matchPath does no ranking of its own (unlike matchRoutes in a data router),
 * and '/bid-templates/:id' happily matches '/bid-templates/new' with id="new".
 * Sorting by static-segment count first makes the literal route win.
 */
const RANKED_PATTERNS = Object.keys(CRUMB_CONFIG).sort((a, b) => {
  const segs = (p: string) => p.split('/').filter(Boolean);
  const statics = (p: string) => segs(p).filter((s) => !s.startsWith(':')).length;
  return statics(b) - statics(a) || segs(b).length - segs(a).length;
});

/**
 * Builds the crumb trail for a pathname by walking the parent chain of the
 * matched route. Returns [] for an unconfigured path — Breadcrumbs renders
 * nothing on an empty array, so an unknown route shows no trail rather than a
 * misleading one.
 *
 * Pure: entity labels come back as descriptors, and useBreadcrumbs resolves
 * them against the query cache.
 */
export function resolveTrail(pathname: string, ctx: TrailContext): CrumbDescriptor[] {
  const pattern = RANKED_PATTERNS.find((p) => matchPath(p, pathname));
  if (!pattern) return [];

  const params = matchPath(pattern, pathname)!.params;

  const chain: string[] = [];
  let current: string | undefined = pattern;
  while (current) {
    // A cycle in the config would otherwise hang the render.
    if (chain.includes(current)) break;
    chain.unshift(current);
    // Annotated: without it the inference of `parent` runs through `current`,
    // which is assigned from `parent`, and tsc reports a circular initializer.
    const parent: CrumbConfig['parent'] = CRUMB_CONFIG[current]?.parent;
    current = typeof parent === 'function' ? parent(ctx) : parent;
  }

  return chain.map((p, i) => {
    const configured = CRUMB_CONFIG[p].label;
    const id = typeof configured === 'string' ? undefined : params[configured.param];
    const isLast = i === chain.length - 1;
    // The rung below this one names the tab it lives in, if its parent has tabs.
    const query = (!isLast && CRUMB_CONFIG[chain[i + 1]].parentQuery) || '';

    return {
      label:
        typeof configured === 'string'
          ? configured
          : id
            ? { entity: configured.entity, id, fallback: configured.fallback }
            : configured.fallback,
      // Ancestor patterns always use a subset of the matched route's params
      // (ROUTES consistently names the project param ':id'), so generatePath
      // cannot come up short.
      href: isLast ? undefined : generatePath(p, params) + query,
    };
  });
}
