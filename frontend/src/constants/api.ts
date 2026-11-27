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
  USER_RESTORE: (id: string) => `/users/${id}/restore`,
  USER_RESEND_INVITE: (id: string) => `/users/${id}/resend-invite`,
  USER_ROLES: (id: string) => `/users/${id}/roles`,

  // Vendors
  VENDORS: '/vendors',
  VENDOR_STATES: '/vendors/states',
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
  PROJECT_STATES: '/projects/states',
  PROJECT: (id: string) => `/projects/${id}`,

  // Tasks (project-scoped)
  PROJECT_TASKS: (projectId: string) => `/projects/${projectId}/tasks`,
  PROJECT_TASK: (projectId: string, taskId: string) => `/projects/${projectId}/tasks/${taskId}`,
  PROJECT_TASKS_REORDER: (projectId: string) => `/projects/${projectId}/tasks/reorder`,
  PROJECT_DEFAULT_TASKS: (projectId: string) => `/projects/${projectId}/tasks/default`,

  // Project notes (rich text)
  PROJECT_NOTES: (projectId: string) => `/projects/${projectId}/notes`,
  PROJECT_NOTE: (noteId: string) => `/project-notes/${noteId}`,

  // Trades (and subtrades)
  TRADES: '/trades',
  TRADE: (id: string) => `/trades/${id}`,
  TRADE_USAGE: (id: string) => `/trades/${id}/usage`,

  // Contract signers (admin-only writes; reads go direct to Supabase under RLS)
  CONTRACT_SIGNERS: '/contract-signers',
  CONTRACT_SIGNER: (id: string) => `/contract-signers/${id}`,

  // Financial module — budgets (admin-only writes; reads go direct to Supabase views)
  PROJECT_BUDGET: (projectId: string) => `/projects/${projectId}/budget`,
  PROJECT_BUDGET_BASELINE: (projectId: string) => `/projects/${projectId}/budget/baseline`,
  PROJECT_BUDGET_SYNC_AWARDS: (projectId: string) => `/projects/${projectId}/budget/sync-awards`,
  PROJECT_BUDGET_RESET: (projectId: string) => `/projects/${projectId}/budget/reset`,
  PROJECT_BUDGET_LINES: (projectId: string) => `/projects/${projectId}/budget/lines`,
  PROJECT_BUDGET_LINES_ORDER: (projectId: string) => `/projects/${projectId}/budget/lines/order`,
  PROJECT_BUDGET_EXPORT: (projectId: string) => `/projects/${projectId}/budget/export`,
  PROJECT_BUDGET_IMPORT_PREVIEW: (projectId: string) => `/projects/${projectId}/budget/import/preview`,
  PROJECT_BUDGET_IMPORT_APPLY: (projectId: string) => `/projects/${projectId}/budget/import/apply`,
  BUDGET_LINE: (lineId: string) => `/budget-lines/${lineId}`,
  BUDGET_LINE_CLOSINGS: (lineId: string) => `/budget-lines/${lineId}/closings`,
  LAND_CLOSING: (closingId: string) => `/land-closings/${closingId}`,
  BUDGET_TEMPLATE_LINES: (templateId: string) => `/budget-templates/${templateId}/lines`,
  BUDGET_TEMPLATE_LINES_ORDER: (templateId: string) => `/budget-templates/${templateId}/lines/order`,
  BUDGET_TEMPLATE_LINE: (lineId: string) => `/budget-template-lines/${lineId}`,

  // Financial module — internal invoices
  PROJECT_INVOICES: (projectId: string) => `/projects/${projectId}/invoices`,
  INVOICE: (invoiceId: string) => `/invoices/${invoiceId}`,
  INVOICE_CATEGORISE: (invoiceId: string) => `/invoices/${invoiceId}/categorise`,
  INVOICE_CANCEL: (invoiceId: string) => `/invoices/${invoiceId}/cancel`,
  INVOICE_URL: (invoiceId: string) => `/invoices/${invoiceId}/url`,

  // Financial module — contingency engine (Phase 3)
  PROJECT_CONTINGENCY: (projectId: string) => `/projects/${projectId}/contingency`,
  PROJECT_CONTINGENCY_LEDGER: (projectId: string) => `/projects/${projectId}/contingency/ledger`,
  PROJECT_CONTINGENCY_LEDGER_EXPORT: (projectId: string) => `/projects/${projectId}/contingency/ledger/export`,
  PROJECT_CONTINGENCY_PERCENT: (projectId: string) => `/projects/${projectId}/contingency/percent`,
  PROJECT_CONTINGENCY_TOP_UPS: (projectId: string) => `/projects/${projectId}/contingency/top-ups`,
  CONTINGENCY_TOP_UP_DECISION: (bucketId: string) => `/contingency-top-ups/${bucketId}/decision`,
  CONTINGENCY_TOP_UP_CANCEL: (bucketId: string) => `/contingency-top-ups/${bucketId}/cancel`,
  PROJECT_BIDDING_CHECKPOINT: (projectId: string) => `/projects/${projectId}/bidding/checkpoint`,
  PROJECT_BIDDING_COMPLETE: (projectId: string) => `/projects/${projectId}/bidding/complete`,
  PROJECT_BIDDING_REOPEN: (projectId: string) => `/projects/${projectId}/bidding/reopen`,
  CONTINGENCY_SETTINGS: '/financial-settings/contingency',

  // Financial module — long-tail items (Phase 7)
  PROJECT_LONG_TAIL: (projectId: string) => `/projects/${projectId}/long-tail`,
  PROJECT_ESCROWS: (projectId: string) => `/projects/${projectId}/escrows`,
  ESCROW: (id: string) => `/escrows/${id}`,
  ESCROW_TRANSITION: (id: string) => `/escrows/${id}/transition`,
  ESCROW_DEFECTS: (id: string) => `/escrows/${id}/defects`,
  ESCROW_RENEW: (id: string) => `/escrows/${id}/renew`,
  ESCROW_DOCUMENT: (id: string) => `/escrows/${id}/document`,
  PROJECT_PROPERTY_TAXES: (projectId: string) => `/projects/${projectId}/property-taxes`,
  PROJECT_TAX_SOLD_PORTION: (projectId: string) => `/projects/${projectId}/property-taxes/sold-portion`,
  PROPERTY_TAX: (id: string) => `/property-taxes/${id}`,
  JURISDICTIONS: '/jurisdictions',
  JURISDICTION: (id: string) => `/jurisdictions/${id}`,

  // Financial module — payment approvals and finance hand-off (Phase 6)
  PAYMENT_APPROVALS: '/payment-approvals',
  PAYMENT_APPROVAL: (id: string) => `/payment-approvals/${id}`,
  BUDGET_LINE_PAYMENTS: (lineId: string) => `/budget-lines/${lineId}/payments`,
  FINANCE_HANDOFFS: '/finance-handoffs',
  FINANCE_HANDOFFS_EXPORT: '/finance-handoffs/export',
  FINANCE_HANDOFFS_MARK_EXPORTED: '/finance-handoffs/mark-exported',
  FINANCE_HANDOFF_RESEND: (id: string) => `/finance-handoffs/${id}/resend`,
  FINANCE_HANDOFF_DOCUMENT: (id: string) => `/finance-handoffs/${id}/document`,
  APPROVER_SETTINGS: '/approval-settings',
  USER_APPROVER_SETTINGS: (id: string) => `/users/${id}/approval-settings`,

  // Financial module — contingency health and alerts (Phase 5)
  PROJECT_FINANCIAL_HEALTH: (projectId: string) => `/projects/${projectId}/financial-health`,
  PROJECT_FINANCIAL_HEALTH_SETUP: (projectId: string) => `/projects/${projectId}/financial-health/setup`,
  PROJECT_GROUNDBREAKING: (projectId: string) => `/projects/${projectId}/financial-health/groundbreaking`,
  PROJECT_LIFT_HOLD: (projectId: string) => `/projects/${projectId}/financial-health/lift-hold`,
  FINANCIAL_ALERTS: '/financial-alerts',
  FINANCIAL_ALERT: (id: string) => `/financial-alerts/${id}`,
  FINANCIAL_ALERT_DECISION: (id: string) => `/financial-alerts/${id}/decision`,

  // Financial module — variances (Phase 4)
  VARIANCES: '/variances',
  VARIANCE: (id: string) => `/variances/${id}`,
  VARIANCE_CANCEL: (id: string) => `/variances/${id}/cancel`,
  VARIANCE_APPROVE: (id: string) => `/variances/${id}/approve`,
  VARIANCE_REJECT: (id: string) => `/variances/${id}/reject`,
  BUDGET_LINE_VARIANCES: (lineId: string) => `/budget-lines/${lineId}/variances`,

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
  // Delivers a contract that was never delivered (the post-commit send failed).
  // Not a resend: an award that already has an envelope is a server-side no-op.
  AWARD_SEND_CONTRACT: (awardId: string) => `/awards/${awardId}/send-contract`,

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
