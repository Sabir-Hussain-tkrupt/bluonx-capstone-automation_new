import { describe, expect, it } from 'vitest';
import { ROUTES } from '@/constants/routes';
import { CRUMB_CONFIG, resolveTrail, type CrumbDescriptor } from '@/lib/breadcrumbs';

const PROJECT = '11111111-1111-4111-8111-111111111111';
const TASK = '22222222-2222-4222-8222-222222222222';
const PKG = '33333333-3333-4333-8333-333333333333';
const MILESTONE = '44444444-4444-4444-8444-444444444444';
const VENDOR = '55555555-5555-4555-8555-555555555555';
const TEMPLATE = '66666666-6666-4666-8666-666666666666';

/** Flattens a trail to [label, href] pairs; entity labels show as `{entity}`. */
function shape(trail: CrumbDescriptor[]): [string, string | undefined][] {
  return trail.map((c) => [
    typeof c.label === 'string' ? c.label : `{${c.label.entity}:${c.label.id}}`,
    c.href,
  ]);
}

describe('resolveTrail', () => {
  it('renders the dashboard as a single unlinked crumb', () => {
    expect(shape(resolveTrail('/dashboard'))).toEqual([['Dashboard', undefined]]);
  });

  it('builds the vendor trail', () => {
    expect(shape(resolveTrail(`/vendors/${VENDOR}`))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Vendors', '/vendors'],
      [`{vendor:${VENDOR}}`, undefined],
    ]);
    expect(shape(resolveTrail('/vendors'))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Vendors', undefined],
    ]);
  });

  it('builds the project trail', () => {
    expect(shape(resolveTrail('/projects'))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', undefined],
    ]);
    expect(shape(resolveTrail(`/projects/${PROJECT}`))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, undefined],
    ]);
    expect(shape(resolveTrail(`/projects/${PROJECT}/tasks`))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}?tab=tasks`],
      ['Tasks', undefined],
    ]);
  });

  it('parents task detail to the project, skipping the /tasks rung', () => {
    expect(shape(resolveTrail(`/projects/${PROJECT}/tasks/${TASK}`))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}?tab=tasks`],
      [`{task:${TASK}}`, undefined],
    ]);
  });

  it('builds the bid package trails', () => {
    const base = `/projects/${PROJECT}/tasks/${TASK}`;

    expect(shape(resolveTrail(`${base}/create-bid-package`))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}?tab=tasks`],
      [`{task:${TASK}}`, base],
      ['New Bid Package', undefined],
    ]);

    expect(shape(resolveTrail(`${base}/bid-packages/${PKG}`))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}?tab=tasks`],
      [`{task:${TASK}}`, base],
      [`{bidPackage:${PKG}}`, undefined],
    ]);

    expect(shape(resolveTrail(`${base}/bid-packages/${PKG}/compare`))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}?tab=tasks`],
      [`{task:${TASK}}`, base],
      [`{bidPackage:${PKG}}`, `${base}/bid-packages/${PKG}`],
      ['Compare', undefined],
    ]);
  });

  it('caps milestone detail at five crumbs, none of them a dead URL namespace', () => {
    const trail = resolveTrail(
      `/projects/${PROJECT}/tasks/${TASK}/milestones/${MILESTONE}`,
    );

    expect(shape(trail)).toEqual([
      ['Dashboard', '/dashboard'],
      ['Projects', '/projects'],
      [`{project:${PROJECT}}`, `/projects/${PROJECT}?tab=tasks`],
      [`{task:${TASK}}`, `/projects/${PROJECT}/tasks/${TASK}`],
      [`{milestone:${MILESTONE}}`, undefined],
    ]);
    // The regression this whole change exists for: `.../milestones` and
    // `.../bid-packages` are URL namespaces with no route, and used to be
    // rendered as crumbs linking to the 404 catch-all.
    expect(trail.every((c) => !c.href?.endsWith('/milestones'))).toBe(true);
  });

  it('builds the flat list trails', () => {
    expect(shape(resolveTrail('/milestones'))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Milestones', undefined],
    ]);
    expect(shape(resolveTrail('/bid-packages'))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Bid Packages', undefined],
    ]);
    expect(shape(resolveTrail('/notifications'))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Notifications', undefined],
    ]);
  });

  it('builds the bid template trails', () => {
    expect(shape(resolveTrail('/bid-templates'))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Bid Templates', undefined],
    ]);
    expect(shape(resolveTrail(`/bid-templates/${TEMPLATE}`))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Bid Templates', '/bid-templates'],
      [`{bidTemplate:${TEMPLATE}}`, undefined],
    ]);
    expect(shape(resolveTrail(`/bid-templates/${TEMPLATE}/edit`))).toEqual([
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
    expect(shape(resolveTrail('/bid-templates/new'))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Bid Templates', '/bid-templates'],
      ['New Template', undefined],
    ]);
  });

  it('builds the settings trails', () => {
    expect(shape(resolveTrail('/settings'))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Settings', undefined],
    ]);
    expect(shape(resolveTrail('/settings/trades'))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Settings', '/settings'],
      ['Trades', undefined],
    ]);
    expect(shape(resolveTrail('/settings/users'))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Settings', '/settings'],
      ['Users', undefined],
    ]);
  });

  it('builds the calendar trail under Settings', () => {
    expect(shape(resolveTrail('/settings/calendar'))).toEqual([
      ['Dashboard', '/dashboard'],
      ['Settings', '/settings'],
      ['Holiday Calendar', undefined],
    ]);
  });

  it('points the parent crumb at the tab that contains the child', () => {
    // The project page's tabs live in the URL, and browser back restores
    // ?tab=tasks. Without this the breadcrumb would quietly disagree with the
    // back button and drop the user on Overview.
    const projectCrumb = (path: string) => resolveTrail(path)[2].href;

    expect(projectCrumb(`/projects/${PROJECT}/tasks/${TASK}`))
      .toBe(`/projects/${PROJECT}?tab=tasks`);
    // Applies at any depth: the rung below the project is still the task.
    expect(projectCrumb(`/projects/${PROJECT}/tasks/${TASK}/milestones/${MILESTONE}`))
      .toBe(`/projects/${PROJECT}?tab=tasks`);
    // And not where the child does not sit in a tab.
    expect(resolveTrail(`/bid-templates/${TEMPLATE}/edit`)[1].href)
      .toBe('/bid-templates');
  });

  it('returns nothing for an unconfigured path', () => {
    // Breadcrumbs renders null on an empty array, so an unknown route shows no
    // trail rather than a misleading one.
    expect(resolveTrail('/nope')).toEqual([]);
    expect(resolveTrail('/bid/some-token')).toEqual([]);
    expect(resolveTrail('/login')).toEqual([]);
  });
});

describe('CRUMB_CONFIG drift guards', () => {
  it('every declared parent is itself a configured route', () => {
    for (const [pattern, config] of Object.entries(CRUMB_CONFIG)) {
      const parent = config.parent;
      if (parent === undefined) continue;
      expect(CRUMB_CONFIG, `${pattern} declares an unknown parent ${parent}`)
        .toHaveProperty([parent]);
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
