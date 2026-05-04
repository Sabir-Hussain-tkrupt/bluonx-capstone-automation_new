/**
 * Centralized React Query key factory.
 *
 * Every query key in the app MUST use this factory. This ensures:
 * 1. No key typos (TypeScript catches misspelled method names)
 * 2. Consistent hierarchy (entity → list/detail → filters)
 * 3. Targeted invalidation (invalidate all vendors, or just one)
 *
 * Key hierarchy:
 *   ['vendors']                    → all vendor queries
 *   ['vendors', 'list']            → all vendor list queries
 *   ['vendors', 'list', { ... }]   → vendor list with specific filters
 *   ['vendors', 'detail', 'uuid']  → single vendor detail
 *
 * Invalidation examples:
 *   queryClient.invalidateQueries({ queryKey: queryKeys.vendors.all })
 *   // ^ invalidates ALL vendor queries (lists + details)
 *
 *   queryClient.invalidateQueries({ queryKey: queryKeys.vendors.lists() })
 *   // ^ invalidates all vendor lists but not details
 */
export const queryKeys = {
  vendors: {
    all: ['vendors'] as const,
    lists: () => [...queryKeys.vendors.all, 'list'] as const,
    list: (filters?: Record<string, unknown>) =>
      filters
        ? ([...queryKeys.vendors.lists(), filters] as const)
        : queryKeys.vendors.lists(),
    details: () => [...queryKeys.vendors.all, 'detail'] as const,
    detail: (id: string) => [...queryKeys.vendors.details(), id] as const,
  },

  projects: {
    all: ['projects'] as const,
    lists: () => [...queryKeys.projects.all, 'list'] as const,
    list: (filters?: Record<string, unknown>) =>
      filters
        ? ([...queryKeys.projects.lists(), filters] as const)
        : queryKeys.projects.lists(),
    details: () => [...queryKeys.projects.all, 'detail'] as const,
    detail: (id: string) => [...queryKeys.projects.details(), id] as const,
  },

  tasks: {
    all: ['tasks'] as const,
    lists: () => [...queryKeys.tasks.all, 'list'] as const,
    list: (filters?: { projectId?: string }) =>
      filters
        ? ([...queryKeys.tasks.lists(), filters] as const)
        : queryKeys.tasks.lists(),
    details: () => [...queryKeys.tasks.all, 'detail'] as const,
    detail: (id: string) => [...queryKeys.tasks.details(), id] as const,
  },

  trades: {
    all: ['trades'] as const,
    lists: () => [...queryKeys.trades.all, 'list'] as const,
    list: (filters?: Record<string, unknown>) =>
      filters
        ? ([...queryKeys.trades.lists(), filters] as const)
        : queryKeys.trades.lists(),
  },

  vendorContacts: {
    all: (vendorId: string) => ['vendors', vendorId, 'contacts'] as const,
    list: (vendorId: string) => [...queryKeys.vendorContacts.all(vendorId), 'list'] as const,
  },

  vendorTrades: {
    all: (vendorId: string) => ['vendors', vendorId, 'trades'] as const,
    list: (vendorId: string) => [...queryKeys.vendorTrades.all(vendorId), 'list'] as const,
  },

  bidTemplates: {
    all: ['bid_templates'] as const,
    lists: () => [...queryKeys.bidTemplates.all, 'list'] as const,
    list: (filters?: Record<string, unknown>) =>
      filters
        ? ([...queryKeys.bidTemplates.lists(), filters] as const)
        : queryKeys.bidTemplates.lists(),
    details: () => [...queryKeys.bidTemplates.all, 'detail'] as const,
    detail: (id: string) => [...queryKeys.bidTemplates.details(), id] as const,
  },

  bidPackages: {
    all: ['bid_packages'] as const,
    lists: () => [...queryKeys.bidPackages.all, 'list'] as const,
    list: (filters?: { taskId?: string }) =>
      filters
        ? ([...queryKeys.bidPackages.lists(), filters] as const)
        : queryKeys.bidPackages.lists(),
    details: () => [...queryKeys.bidPackages.all, 'detail'] as const,
    detail: (id: string) => [...queryKeys.bidPackages.details(), id] as const,
    forTask: (taskId: string) => [...queryKeys.bidPackages.all, 'task', taskId] as const,
  },

  qualifiedVendors: {
    all: (taskId: string) => ['qualified_vendors', taskId] as const,
  },

  projectDocuments: {
    all: (projectId: string) => ['projects', projectId, 'documents'] as const,
  },

  bidInvitations: {
    emailLog: (bidPackageId: string) => ['bid_packages', bidPackageId, 'email_log'] as const,
  },

  bidSubmissions: {
    all: ['bid_submissions'] as const,
    lists: () => [...queryKeys.bidSubmissions.all, 'list'] as const,
    list: (filters?: { taskId?: string; bidPackageId?: string }) =>
      filters
        ? ([...queryKeys.bidSubmissions.lists(), filters] as const)
        : queryKeys.bidSubmissions.lists(),
    details: () => [...queryKeys.bidSubmissions.all, 'detail'] as const,
    detail: (id: string) => [...queryKeys.bidSubmissions.details(), id] as const,
  },

  awards: {
    all: ['awards'] as const,
    lists: () => [...queryKeys.awards.all, 'list'] as const,
    list: (filters?: { taskId?: string }) =>
      filters
        ? ([...queryKeys.awards.lists(), filters] as const)
        : queryKeys.awards.lists(),
    details: () => [...queryKeys.awards.all, 'detail'] as const,
    detail: (id: string) => [...queryKeys.awards.details(), id] as const,
  },

  contracts: {
    all: ['contracts'] as const,
    lists: () => [...queryKeys.contracts.all, 'list'] as const,
    list: (filters?: Record<string, unknown>) =>
      filters
        ? ([...queryKeys.contracts.lists(), filters] as const)
        : queryKeys.contracts.lists(),
    details: () => [...queryKeys.contracts.all, 'detail'] as const,
    detail: (id: string) => [...queryKeys.contracts.details(), id] as const,
  },

  milestones: {
    all: ['milestones'] as const,
    lists: () => [...queryKeys.milestones.all, 'list'] as const,
    list: (filters?: { contractId?: string; taskId?: string }) =>
      filters
        ? ([...queryKeys.milestones.lists(), filters] as const)
        : queryKeys.milestones.lists(),
    details: () => [...queryKeys.milestones.all, 'detail'] as const,
    detail: (id: string) => [...queryKeys.milestones.details(), id] as const,
  },

  nearbyVendors: {
    all: (projectId: string) => ['projects', projectId, 'nearby-vendors'] as const,
    list: (projectId: string, filters?: { radius?: number; tradeId?: string }) =>
      filters
        ? ([...queryKeys.nearbyVendors.all(projectId), filters] as const)
        : queryKeys.nearbyVendors.all(projectId),
  },

  notifications: {
    all: ['notifications'] as const,
    lists: () => [...queryKeys.notifications.all, 'list'] as const,
    list: (filters?: { userId?: string }) =>
      filters
        ? ([...queryKeys.notifications.lists(), filters] as const)
        : queryKeys.notifications.lists(),
  },

  dashboard: {
    all: ['dashboard'] as const,
    openTaskCount: () => [...queryKeys.dashboard.all, 'openTaskCount'] as const,
    pendingBidCount: () => [...queryKeys.dashboard.all, 'pendingBidCount'] as const,
  },
} as const;
