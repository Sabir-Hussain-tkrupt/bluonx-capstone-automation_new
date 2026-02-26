# Current Phase Tasks — BluOnX Bid Management System

**Last Updated:** February 25, 2026

---

## Phase 1: Foundation & Database (60 Hours) — ✅ COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| 1.1 — Supabase project setup | ✅ | Environment configured (free tier dev account) |
| 1.2 — Core database schema | ✅ | `database/bluonx_complete_schema_v2_2.sql` — 28 tables |
| 1.3 — Database indexes | ✅ | 49 custom indexes in schema file Section 5 |
| 1.4 — Row Level Security | ✅ | `database/rls_policies.sql` — 28 SELECT + 8 WRITE policies |
| 1.5 — Database triggers | ✅ | 25 triggers, 11 functions in schema file Section 6 |
| 1.6 — Storage buckets | ✅ | 3 private buckets, 12 storage policies |
| 1.7 — Auth framework | ⏳ | Supabase Auth configured, frontend integration in Phase 2 |
| 1.8 — Dev/staging environments | ⏳ | Using free-tier dev account; prod setup deferred |
| 1.9 — AWS infrastructure | ⏳ | Deferred to Phase 2 / deployment phase |

---

## Phase 2: Frontend Foundation, Backend API & Auth (100 Hours) — 🔄 IN PROGRESS

### Task 2.1 — React + Vite + TailwindCSS v4 (4h) ✅ COMPLETE
- Vite project scaffold with TypeScript
- TailwindCSS v4 configured (CSS-first, `@theme` in app.css)
- Feature-based directory structure established
- Path aliases configured (`@/` → `src/`)

### Task 2.2 — Routing with React Router v6 (6h) ⏳ NEXT
- Define route structure for all major pages
- Protected route component (redirect to `/login` if no session)
- Navigation guards for role-based access
- **Routes needed:**
  - `/login`, `/register`, `/forgot-password`
  - `/dashboard`
  - `/vendors`, `/vendors/:id`
  - `/projects`, `/projects/:id`
  - `/projects/:id/tasks`, `/projects/:id/tasks/:taskId`
  - `/projects/:id/tasks/:taskId/bids`
  - `/projects/:id/tasks/:taskId/award`
  - `/settings` (admin: user management, trade management)

### Task 2.3 — Supabase Client + State Management (5h)
- Initialize Supabase client with env vars (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`)
- Auth state management (session listener, auto-refresh)
- Auth context provider wrapping the app
- Real-time subscription setup (for later use in bid tracking dashboard)

### Task 2.4 — React Query for API Layer (6h)
- React Query provider and configuration
- Custom hooks pattern for data fetching
- Cache invalidation strategies
- Separate hooks for Supabase direct reads vs FastAPI calls
- **Pattern:**
  ```typescript
  // Supabase direct read (RLS protected)
  const useVendors = () => useQuery({ queryKey: ['vendors'], queryFn: fetchVendors })

  // FastAPI write operation
  const useCreateVendor = () => useMutation({ mutationFn: createVendor, onSuccess: () => queryClient.invalidateQueries(['vendors']) })
  ```

### Task 2.5 — Reusable UI Component Library (15h)
- **Inputs:** Button, TextInput, Select, Checkbox, RadioGroup, DatePicker, FileUpload
- **Layout:** Card, Modal/Dialog, Alert/Toast, Tabs, Accordion
- **Data:** Table (with sorting, filtering, pagination), StatusBadge, EmptyState, Skeleton/Loading
- **Navigation:** Sidebar, Breadcrumbs, TopHeader, UserMenu
- **Forms:** FormField wrapper, validation error display
- All components should use TailwindCSS v4 utility classes
- Consistent sizing, spacing, and color tokens from `@theme`

### Task 2.6 — FastAPI Backend on AWS (25h)
- FastAPI project structure in `backend/`
- Supabase connection using `service_role` key
- API endpoint scaffolding for all resources (vendors, projects, tasks, bids, contracts, milestones)
- CORS configuration for frontend domain
- JWT validation middleware (validate Supabase Auth tokens)
- Role-based authorization decorators
- Docker configuration for deployment
- **Architecture:** FastAPI is the security gatekeeper for all writes and vendor portal access

### Task 2.7 — Authentication System (25h)
- **Frontend flows:**
  - Login (email/password → Supabase Auth)
  - Register (with full_name and role in metadata → triggers `fn_handle_new_auth_user`)
  - Password reset (Supabase magic link for reset, NOT for regular login)
  - Email verification
  - Session persistence (token storage, auto-refresh, logout)
- **Protected routes:**
  - `<ProtectedRoute>` HOC checking auth session
  - Role-based UI rendering (admin sees user/trade management, PM doesn't)
  - Redirect to `/login` on session expiry
- **No OAuth/Google Sign-In** — confirmed out of scope

### Task 2.8 — Main Dashboard Layout (8h)
- Sidebar navigation with icons and active state
- Top header with user menu (profile, logout)
- Breadcrumb navigation
- Responsive: hamburger menu on mobile
- Layout wrapper component for all authenticated pages

### Task 2.9 — Responsive Design (6h)
- Mobile (320px+), tablet (768px+), desktop (1024px+) breakpoints
- Touch-friendly UI elements (min 44px tap targets)
- Mobile navigation patterns (bottom nav or hamburger)
- Tables collapse to card views on mobile

---

## Phase 2 Acceptance Criteria

- [ ] React app running locally and building for production
- [ ] Email/password auth fully functional (login, register, reset)
- [ ] Session persistence working (users stay logged in across refreshes)
- [ ] Protected routes redirect unauthenticated users to login
- [ ] Clean responsive UI with consistent design system
- [ ] Reusable component library ready for Phase 3 CRUD pages
- [ ] Supabase client reading data correctly through RLS
- [ ] React Query hooks pattern established for data fetching
- [ ] FastAPI backend scaffolded with Supabase connection
- [ ] CORS configured for frontend ↔ backend communication
- [ ] Routing structure in place for all major pages

---

## Phase 3 Preview: Core Entity Management (60h)

_Not started. For planning context only._

- 3.1 — Vendor management (list, CRUD, CSV import, detail page)
- 3.2 — Project management (list, CRUD, document upload, budget tracking)
- 3.3 — Task management within projects (CRUD, sequencing, budget per task)
- 3.4 — Document upload functionality (drag-drop, preview, secure URLs)
- 3.5 — Google Maps integration (geocoding, distance calc, radius filtering)

---

## Full Project Plan

The complete 12-phase project plan (700 hours, 11 weeks) is available at `docs/PROJECT_PLAN.pdf`.
Phases 4–12 cover: Bid Invitations, Bid Collection Portal, Real-Time Dashboard, Reminder System, Bid Comparison & Scoring, Awards & Contracts, Milestone Tracking, Testing, and Deployment.
