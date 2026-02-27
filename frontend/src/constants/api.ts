/**
 * FastAPI endpoint paths (relative to /api/v1).
 *
 * Used with the `api` Axios instance from @/lib/api,
 * which has baseURL = VITE_API_BASE_URL/api/v1.
 *
 * Backend is not built yet (Task 2.6). These establish the convention.
 */
export const API_ENDPOINTS = {
  // Vendors
  VENDORS: '/vendors',
  VENDOR: (id: string) => `/vendors/${id}`,

  // Projects
  PROJECTS: '/projects',
  PROJECT: (id: string) => `/projects/${id}`,

  // Tasks
  TASKS: '/tasks',
  TASK: (id: string) => `/tasks/${id}`,

  // Trades
  TRADES: '/trades',
  TRADE: (id: string) => `/trades/${id}`,

  // Bid Packages
  BID_PACKAGES: '/bid-packages',
  BID_PACKAGE: (id: string) => `/bid-packages/${id}`,

  // Bid Invitations
  BID_INVITATIONS: '/bid-invitations',
  BID_INVITATION: (id: string) => `/bid-invitations/${id}`,

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
