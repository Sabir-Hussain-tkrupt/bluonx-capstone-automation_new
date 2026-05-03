/**
 * FastAPI endpoint paths (relative to /api/v1).
 *
 * Used with the `api` Axios instance from @/lib/api,
 * which has baseURL = VITE_API_BASE_URL/api/v1.
 *
 */
export const API_ENDPOINTS = {
  // Vendors
  VENDORS: '/vendors',
  VENDOR: (id: string) => `/vendors/${id}`,
  VENDOR_CONTACTS: (vendorId: string) => `/vendors/${vendorId}/contacts`,
  VENDOR_CONTACT: (vendorId: string, contactId: string) => `/vendors/${vendorId}/contacts/${contactId}`,
  VENDOR_TRADES_ENDPOINT: (vendorId: string) => `/vendors/${vendorId}/trades`,
  VENDOR_TRADE: (vendorId: string, tradeId: string) => `/vendors/${vendorId}/trades/${tradeId}`,
  VENDOR_IMPORT: '/vendors/import',

  // Projects
  PROJECTS: '/projects',
  PROJECT: (id: string) => `/projects/${id}`,
  NEARBY_VENDORS: (projectId: string) => `/projects/${projectId}/nearby-vendors`,

  // Tasks (project-scoped)
  PROJECT_TASKS: (projectId: string) => `/projects/${projectId}/tasks`,
  PROJECT_TASK: (projectId: string, taskId: string) => `/projects/${projectId}/tasks/${taskId}`,
  PROJECT_TASKS_REORDER: (projectId: string) => `/projects/${projectId}/tasks/reorder`,

  // Trades
  TRADES: '/trades',
  TRADE: (id: string) => `/trades/${id}`,

  // Bid Templates
  BID_TEMPLATES: '/bid-templates',
  BID_TEMPLATE: (id: string) => `/bid-templates/${id}`,

  // Qualified Vendors
  TASK_QUALIFIED_VENDORS: (taskId: string) => `/tasks/${taskId}/qualified-vendors`,

  // Bid Packages
  BID_PACKAGES: '/bid-packages',
  BID_PACKAGE: (id: string) => `/bid-packages/${id}`,
  TASK_BID_PACKAGES: (taskId: string) => `/tasks/${taskId}/bid-packages`,
  BID_PACKAGE_INVITATIONS: (id: string) => `/bid-packages/${id}/invitations`,
  BID_PACKAGE_EMAIL_LOG: (id: string) => `/bid-packages/${id}/email-log`,

  // Bid Invitations
  BID_INVITATIONS: '/bid-invitations',
  BID_INVITATION: (id: string) => `/bid-invitations/${id}`,
  BID_INVITATION_RESEND_LINK: (id: string) => `/bid-invitations/${id}/resend-link`,
  BID_INVITATION_STATUS: (id: string) => `/bid-invitations/${id}/status`,

  // Project Documents
  PROJECT_DOCUMENTS: (projectId: string) => `/projects/${projectId}/documents`,

  // Bid Submissions
  BID_SUBMISSIONS: '/bid-submissions',
  BID_SUBMISSION: (id: string) => `/bid-submissions/${id}`,

  // Awards
  AWARDS: '/awards',
  AWARD: (id: string) => `/awards/${id}`,

  // Contracts
  CONTRACTS: '/contracts',
  CONTRACT: (id: string) => `/contracts/${id}`,

  // Milestones
  MILESTONES: '/milestones',
  MILESTONE: (id: string) => `/milestones/${id}`,

  // Notifications
  NOTIFICATIONS: '/notifications',
} as const;
