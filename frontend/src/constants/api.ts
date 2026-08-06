/**
 * FastAPI endpoint paths (relative to /api/v1).
 *
 * Used with the `api` Axios instance from @/lib/api,
 * which has baseURL = VITE_API_BASE_URL/api/v1.
 *
 */
export const API_ENDPOINTS = {
  // Users (admin-only management; all reads AND writes go through FastAPI)
  USERS: '/users',
  USER: (id: string) => `/users/${id}`,
  USER_INVITE: '/users/invite',
  USER_RESEND_INVITE: (id: string) => `/users/${id}/resend-invite`,

  // Vendors
  VENDORS: '/vendors',
  VENDOR: (id: string) => `/vendors/${id}`,
  VENDOR_CONTACTS: (vendorId: string) => `/vendors/${vendorId}/contacts`,
  VENDOR_CONTACT: (vendorId: string, contactId: string) => `/vendors/${vendorId}/contacts/${contactId}`,
  VENDOR_TRADES_ENDPOINT: (vendorId: string) => `/vendors/${vendorId}/trades`,
  VENDOR_TRADE: (vendorId: string, tradeId: string) => `/vendors/${vendorId}/trades/${tradeId}`,
  VENDOR_IMPORT: '/vendors/import',
  VENDORS_INSURANCE_EXPIRING_COUNT: '/vendors/insurance-expiring-count',
  VENDOR_EMAIL_LOG: (vendorId: string) => `/vendors/${vendorId}/email-log`,

  // Projects
  PROJECTS: '/projects',
  PROJECT: (id: string) => `/projects/${id}`,

  // Tasks (project-scoped)
  PROJECT_TASKS: (projectId: string) => `/projects/${projectId}/tasks`,
  PROJECT_TASK: (projectId: string, taskId: string) => `/projects/${projectId}/tasks/${taskId}`,
  PROJECT_TASKS_REORDER: (projectId: string) => `/projects/${projectId}/tasks/reorder`,

  // Trades
  TRADES: '/trades',

  // Holidays (admin-only writes; reads go direct to Supabase under RLS)
  HOLIDAYS: '/holidays',
  HOLIDAYS_RANGE: '/holidays/range',
  HOLIDAY: (id: string) => `/holidays/${id}`,

  // Bid Templates
  BID_TEMPLATES: '/bid-templates',
  BID_TEMPLATE: (id: string) => `/bid-templates/${id}`,
  BID_TEMPLATE_DUPLICATE: (id: string) => `/bid-templates/${id}/duplicate`,

  // Qualified Vendors
  TASK_QUALIFIED_VENDORS: (taskId: string) => `/tasks/${taskId}/qualified-vendors`,

  // Bid Packages
  BID_PACKAGES: '/bid-packages',
  BID_PACKAGE: (id: string) => `/bid-packages/${id}`,
  BID_PACKAGE_CLOSE: (id: string) => `/bid-packages/${id}/close`,
  BID_PACKAGE_CANCEL: (id: string) => `/bid-packages/${id}/cancel`,
  TASK_BID_PACKAGES: (taskId: string) => `/tasks/${taskId}/bid-packages`,
  BID_PACKAGE_EMAIL_LOG: (id: string) => `/bid-packages/${id}/email-log`,
  BID_PACKAGE_SCORES: (id: string) => `/bid-packages/${id}/scores`,

  // Bid Invitations
  BID_INVITATION_RESEND_LINK: (id: string) => `/bid-invitations/${id}/resend-link`,
  BID_INVITATION_STATUS: (id: string) => `/bid-invitations/${id}/status`,

  // Project Documents
  PROJECT_DOCUMENTS: (projectId: string) => `/projects/${projectId}/documents`,

  // Bid Submissions
  BID_SUBMISSION: (id: string) => `/bid-submissions/${id}`,

  // Bid Revision Requests
  BID_REVISION_REQUESTS: '/bid-revision-requests',
  BID_REVISION_REQUEST_CANCEL: (id: string) => `/bid-revision-requests/${id}/cancel`,

  // Awards
  AWARDS: '/awards',
  AWARD_VALIDATE: (bidSubmissionId: string) => `/awards/validate/${bidSubmissionId}`,

  // Contracts
  CONTRACT_MARK_COMPLETE: (id: string) => `/contracts/${id}/mark-complete`,
  CONTRACT_REVIEW: (id: string) => `/contracts/${id}/review`,

  // Vendor performance reviews
  REVIEW: (id: string) => `/reviews/${id}`,

  // Milestones
  MILESTONES: '/milestones',
  MILESTONE: (id: string) => `/milestones/${id}`,
  MILESTONE_MARK_STARTED: (id: string) => `/milestones/${id}/mark-started`,
  MILESTONE_MARK_COMPLETED: (id: string) => `/milestones/${id}/mark-completed`,
  MILESTONE_RESCHEDULE: (id: string) => `/milestones/${id}/reschedule`,
  MILESTONE_CANCEL: (id: string) => `/milestones/${id}/cancel`,

  // Notifications
  NOTIFICATIONS: '/notifications',
  NOTIFICATIONS_UNREAD_COUNT: '/notifications/unread-count',
  NOTIFICATIONS_MARK_ALL_READ: '/notifications/mark-all-read',
  NOTIFICATION_READ: (id: string) => `/notifications/${id}/read`,
} as const;
