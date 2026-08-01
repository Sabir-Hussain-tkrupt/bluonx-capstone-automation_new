/**
 * Centralized route path constants.
 * Single source of truth — import ROUTES instead of hardcoding path strings.
 */
export const ROUTES = {
  // Public auth routes
  LOGIN: '/login',
  FORGOT_PASSWORD: '/forgot-password',

  // Auth callback routes (Supabase redirects here)
  AUTH_CALLBACK: '/auth/callback',
  AUTH_RESET_PASSWORD: '/auth/reset-password',
  // Invited user sets their password (bare route — arrives authenticated, passwordless)
  ACCEPT_INVITE: '/accept-invite',

  // Protected routes
  DASHBOARD: '/dashboard',
  VENDORS: '/vendors',
  VENDOR_DETAIL: '/vendors/:id',
  PROJECTS: '/projects',
  PROJECT_DETAIL: '/projects/:id',
  TASKS: '/projects/:id/tasks',
  TASK_DETAIL: '/projects/:id/tasks/:taskId',
  BID_PACKAGES: '/bid-packages',
  BID_TEMPLATES: '/bid-templates',
  BID_TEMPLATE_NEW: '/bid-templates/new',
  BID_TEMPLATE_DETAIL: '/bid-templates/:id',
  BID_TEMPLATE_EDIT: '/bid-templates/:id/edit',
  CREATE_BID_PACKAGE: '/projects/:id/tasks/:taskId/create-bid-package',
  BID_PACKAGE_DETAIL: '/projects/:id/tasks/:taskId/bid-packages/:bidPackageId',
  BID_PACKAGE_COMPARE: '/projects/:id/tasks/:taskId/bid-packages/:bidPackageId/compare',
  MILESTONE_DETAIL: '/projects/:id/tasks/:taskId/milestones/:milestoneId',
  MILESTONES: '/milestones',
  NOTIFICATIONS: '/notifications',
  SETTINGS: '/settings',
  SETTINGS_TRADES: '/settings/trades',
  SETTINGS_USERS: '/settings/users',
  SETTINGS_CALENDAR: '/settings/calendar',

  // Error pages
  UNAUTHORIZED: '/unauthorized',

  // ─── Vendor Portal (public, isolated from admin layout) ─────────
  PORTAL_LANDING: '/bid/:token',
  PORTAL_REVISION: '/bid/revision',
  PORTAL_FORM: '/bid/form',
  PORTAL_SUBMITTED: '/bid/submitted/:id',
  PORTAL_REVISION_INACTIVE: '/bid/revision-unavailable',
  PORTAL_REVISION_DECLINED: '/bid/revision-declined',
  PORTAL_EXPIRED: '/bid/expired',
  PORTAL_INVALID: '/bid/invalid',
  PORTAL_CLOSED: '/bid/closed',
  PORTAL_ALREADY_SUBMITTED: '/bid/already-submitted',

  // ─── Milestone check-in (Phase 10.2, own /milestone/* subtree) ───
  PORTAL_MILESTONE_LANDING: '/milestone/:token',
  PORTAL_MILESTONE: '/milestone/respond',
  PORTAL_MILESTONE_RECORDED: '/milestone/recorded',
  PORTAL_MILESTONE_INACTIVE: '/milestone/unavailable',
} as const;
