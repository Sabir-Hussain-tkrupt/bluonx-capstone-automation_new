import { describe, expect, it } from 'vitest';
import { ROUTES } from '@/constants/routes';
import { CRUMB_CONFIG, resolveTrail, type CrumbDescriptor } from '@/lib/breadcrumbs';

const PROJECT = '11111111-1111-4111-8111-111111111111';
const TASK = '22222222-2222-4222-8222-222222222222';
const PKG = '33333333-3333-4333-8333-333333333333';
const MILESTONE = '44444444-4444-4444-8444-444444444444';
const VENDOR = '55555555-5555-4555-8555-555555555555';
const TEMPLATE = '66666666-6666-4666-8666-666666666666';

const asAdmin = { isAdmin: true };
const asPM = { isAdmin: false };

/** Flattens a trail to [label, href] pairs; entity labels show as `{entity}`. */
function shape(trail: CrumbDescriptor[]): [string, string | undefined][] {
  return trail.map((c) => [
    typeof c.label === 'string' ? c.label : `{${c.label.entity}:${c.label.id}}`,
    c.href,
  ]);
}

describe('resolveTrail', () => {
  it('renders the dashboard as a single unlinked crumb', () => {
    expect(shape(resolveTrail('/dashboard', asAdmin))).toEqual([['Dashboard', undefined]]);
  });

  it('builds the vendor trail', () => {
    expect(shape(resolveTrail(`/vendors/${VENDOR}`, asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Vendors', '/vendors'],
      [`{vendor:${VENDOR}}`, undefined],
    ]);
    expect(shape(resolveTrail('/vendors', asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Vendors', undefined],
    ]);
  });

  it('builds the project trail', () => {
    expect(shape(resolveTrail('/projects', asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', undefined],
    ]);
    expect(shape(resolveTrail(`/projects/${PROJECT}`, asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, undefined],
    ]);
    expect(shape(resolveTrail(`/projects/${PROJECT}/tasks`, asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}`],
      ['Tasks', undefined],
    ]);
  });

  it('parents task detail to the project, skipping the /tasks rung', () => {
    expect(shape(resolveTrail(`/projects/${PROJECT}/tasks/${TASK}`, asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}`],
      [`{task:${TASK}}`, undefined],
    ]);
  });

  it('builds the bid package trails', () => {
    const base = `/projects/${PROJECT}/tasks/${TASK}`;

    expect(shape(resolveTrail(`${base}/create-bid-package`, asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}`],
      [`{task:${TASK}}`, base],
      ['New Bid Package', undefined],
    ]);

    expect(shape(resolveTrail(`${base}/bid-packages/${PKG}`, asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}`],
      [`{task:${TASK}}`, base],
      [`{bidPackage:${PKG}}`, undefined],
    ]);

    expect(shape(resolveTrail(`${base}/bid-packages/${PKG}/compare`, asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}`],
      [`{task:${TASK}}`, base],
      [`{bidPackage:${PKG}}`, `${base}/bid-packages/${PKG}`],
      ['Compare', undefined],
    ]);
  });

  it('caps milestone detail at five crumbs, none of them a dead URL namespace', () => {
    const trail = resolveTrail(
      `/projects/${PROJECT}/tasks/${TASK}/milestones/${MILESTONE}`,
      asAdmin,
    );

    expect(shape(trail)).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}`],
      [`{task:${TASK}}`, `/projects/${PROJECT}/tasks/${TASK}`],
      [`{milestone:${MILESTONE}}`, undefined],
    ]);
    // The regression this whole change exists for: `.../milestones` and
    // `.../bid-packages` are URL namespaces with no route, and used to be
    // rendered as crumbs linking to the 404 catch-all.
    expect(trail.every((c) => !c.href?.endsWith('/milestones'))).toBe(true);
  });

  it('builds the flat list trails', () => {
    expect(shape(resolveTrail('/milestones', asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Milestones', undefined],
    ]);
    expect(shape(resolveTrail('/bid-packages', asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Bid Packages', undefined],
    ]);
    expect(shape(resolveTrail('/notifications', asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Notifications', undefined],
    ]);
  });

  it('builds the bid template trails', () => {
    expect(shape(resolveTrail('/bid-templates', asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Bid Templates', undefined],
    ]);
    expect(shape(resolveTrail(`/bid-templates/${TEMPLATE}`, asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Bid Templates', '/bid-templates'],
      [`{bidTemplate:${TEMPLATE}}`, undefined],
    ]);
    expect(shape(resolveTrail(`/bid-templates/${TEMPLATE}/edit`, asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Bid Templates', '/bid-templates'],
      [`{bidTemplate:${TEMPLATE}}`, `/bid-templates/${TEMPLATE}`],
      ['Edit', undefined],
    ]);
  });

  it('prefers the literal /bid-templates/new over /bid-templates/:id', () => {
    // matchPath does no ranking of its own: '/bid-templates/:id' matches
    // '/bid-templates/new' with id="new", which would render the string "new"
    // as a template name and link the crumb at a template that does not exist.
    expect(shape(resolveTrail('/bid-templates/new', asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Bid Templates', '/bid-templates'],
      ['New Template', undefined],
    ]);
  });

  it('builds the settings trails', () => {
    expect(shape(resolveTrail('/settings', asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Settings', undefined],
    ]);
    expect(shape(resolveTrail('/settings/trades', asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Settings', '/settings'],
      ['Trades', undefined],
    ]);
    expect(shape(resolveTrail('/settings/users', asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Settings', '/settings'],
      ['Users', undefined],
    ]);
  });

  it('skips the admin-only Settings rung on the calendar for a PM', () => {
    // /settings/calendar is open to PMs but /settings is admin-gated, so for a
    // PM that crumb would silently bounce them to the dashboard.
    expect(shape(resolveTrail('/settings/calendar', asAdmin))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Settings', '/settings'],
      ['Holiday Calendar', undefined],
    ]);
    expect(shape(resolveTrail('/settings/calendar', asPM))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Holiday Calendar', undefined],
    ]);
  });

  it('returns nothing for an unconfigured path', () => {
    // Breadcrumbs renders null on an empty array, so an unknown route shows no
    // trail rather than a misleading one.
    expect(resolveTrail('/nope', asAdmin)).toEqual([]);
    expect(resolveTrail('/bid/some-token', asAdmin)).toEqual([]);
    expect(resolveTrail('/login', asAdmin)).toEqual([]);
  });
});

describe('CRUMB_CONFIG drift guards', () => {
  it('every declared parent is itself a configured route', () => {
    for (const [pattern, config] of Object.entries(CRUMB_CONFIG)) {
      const parents =
        typeof config.parent === 'function'
          ? [config.parent({ isAdmin: true }), config.parent({ isAdmin: false })]
          : [config.parent];

      for (const parent of parents) {
        if (parent === undefined) continue;
        expect(CRUMB_CONFIG, `${pattern} declares an unknown parent ${parent}`)
          .toHaveProperty([parent]);
      }
    }
  });

  it('covers every route that renders inside DashboardLayout', () => {
    // Routes rendered OUTSIDE DashboardLayout have no breadcrumb at all, so
    // they are deliberately unconfigured. Anything else added to ROUTES must
    // get a crumb entry, or it would silently render nothing.
    const EXCLUDED: string[] = [
      ROUTES.LOGIN,
      ROUTES.FORGOT_PASSWORD,
      ROUTES.AUTH_CALLBACK,
      ROUTES.AUTH_RESET_PASSWORD,
      ROUTES.ACCEPT_INVITE,
      ROUTES.UNAUTHORIZED,
      ...Object.entries(ROUTES)
        .filter(([key]) => key.startsWith('PORTAL_'))
        .map(([, value]) => value),
    ];

    const expected = Object.values(ROUTES)
      .filter((route) => !EXCLUDED.includes(route))
      .sort();

    expect(Object.keys(CRUMB_CONFIG).sort()).toEqual(expected);
  });
});
