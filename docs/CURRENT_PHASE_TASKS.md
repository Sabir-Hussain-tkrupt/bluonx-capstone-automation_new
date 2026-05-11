# Current Phase Tasks — BluOnX Development Operations Platform

**Last Updated:** May 1, 2026

---

## Phase 1: Foundation & Database (60h) — ✅ COMPLETE
## Phase 2: Frontend Foundation, Backend API & Auth (100h) — ✅ COMPLETE
## Phase 3: Core Entity Management (76h) — ✅ COMPLETE
## Phase 4: Bid Invitation System (50h) — ✅ COMPLETE
## Phase 5: Bid Collection — Custom Secure Forms (60h) — ✅ COMPLETE

**Deferred (see `docs/DEFERRED.md`):**
- Task 1.8 — Dev/staging environment separation
- Task 1.9 — AWS infrastructure setup (pending client credentials)

---

## Phase 6: Real-Time Dashboard & Visibility (~30h) — 🔄 IN PROGRESS

**Goal:** Give PMs real visibility surfaces — a proper landing dashboard, a cross-task bid package overview, single-bid inspection, and visual breakdowns of in-flight bids.
 
**Tables read:** `bid_packages`, `bid_invitations`, `bid_submissions`, `bid_line_items`, `bid_attachments`, `tasks`, `projects`, `vendors`, `vendor_contacts`, `magic_link_tokens`
 
**Tables written:** none in Phase 6 proper. (Lifecycle status writes — `opened`, `expired` — were handled as a pre-Phase-6 cleanup pass before this phase started.)


### Architecture Context
 
- **Refresh model — intentional, no changes.** Reads use the existing global QueryClient defaults: `staleTime: 2min`, `refetchOnWindowFocus: true`, `refetchOnMount: true`, `refetchOnReconnect: 'always'`. Mutations invalidate query keys in `onSuccess`. **No polling (`refetchInterval`) and no Supabase Realtime subscriptions are added in Phase 6.** Existing dormant Realtime hooks (`useRealtimeSubscription`, `useRealtimeQueryInvalidation`) remain unused — preserved as post-MVP infrastructure.
- **Reads:** Continue using Supabase JS client with RLS for authenticated dashboard reads. Writes via FastAPI (service_role).
- **Routing:** All new pages live under the existing admin layout and are wrapped by the standard `ProtectedRoute`. No new role-based gating in Phase 6 — both `admin` and `project_manager` see the same surfaces.
- **Charts library:** Recharts (added in Task 6.4).


### Task 6.1: Wire Up Real Dashboard Counts (~3–4h)

**Current state:** `frontend/src/features/dashboard/pages/DashboardPage.tsx` exists as a stub. It shows 4 stat cards — "Active Projects" and "Active Vendors" are wired via Supabase count queries; "Open Tasks" and "Pending Bids" are hardcoded to `--`. Three quick-nav cards link to Vendors, Projects, and Settings.

**Goal:** Make every stat card show real data. Add one more card if the cleanup makes it natural.

**Sub-tasks:**

- **Open Tasks count.** A task is "open" if `tasks.deleted_at IS NULL` AND `tasks.status` is one of `bidding`, `evaluating`, or `awarded` (i.e., active work, not `draft`, `completed`, or `cancelled`). Use a Supabase `count` query, same pattern as the existing two cards.
- **Pending Bids count.** A bid package is "pending" if `bid_packages.status = 'open'`. Count distinct bid packages, not invitations. (Alternative interpretation: count bid packages with at least one invitation in `sent` or `opened` state. Go with the simpler `status = 'open'` reading for v1.)
- **Optional fourth metric: "Awards This Month."** Count of `awards` rows where `awarded_at >= start_of_current_month` and `status` in (`pending_acceptance`, `accepted`). Adds a forward-looking signal without much work. Include if it slots cleanly; skip if the layout fights it.
- **Loading and empty states.** Each card shows a skeleton while loading; shows `0` (not `--`) when data resolves to zero. The hardcoded `--` placeholders go away.
- **No clickability changes** — these are display-only stat cards. The quick-nav cards below already handle navigation.

**Sub-task notes:**
- All four counts run as parallel `useQuery` calls; React Query handles independent loading states naturally.
- Use the existing `staleTime: 2min` default. Do not add `refetchInterval`. Stat cards refresh on tab focus, which is the right cadence.

---
 
### Task 6.2: PM Single Bid Detail View (~6–8h)
 
**Why this exists:** Currently a PM cannot inspect a submitted bid's contents from the Bid Package Detail page — only aggregate counts and totals are visible. This task closes that gap.
 
**Scope:** Single-bid inspection only. No draft visibility, no annotations, no comparison.
 
**Sub-task A: PM-side single submission endpoint**
 
- Implement the existing stub at `GET /api/v1/bid-submissions/{submission_id}` in `backend/app/routers/bid_submissions.py` (currently raises 501).
- Returns full submission shape:
  - Top-level: vendor company name, vendor contact (name, email), `total_amount`, `status`, `vendor_notes`, `submitted_at`, `is_direct_assign`, `bid_invitation_id`.
  - Line items array: `description`, `item_type` (lump_sum / unit_price), `quantity`, `unit_of_measure`, `unit_price`, `lump_sum_amount`, `line_total`, `sort_order`.
  - Attachments array: `file_name`, `file_size`, `file_type`, signed download URL.
- Read-only. user-authed via existing `get_current_active_user`. 404 if submission missing.
- Use the same Supabase Storage signed-URL pattern that the vendor portal uses for project documents — don't reinvent.

**Sub-task B: "View Bid" quick action on invitations table**
 
- Add a "View Bid" button to the actions cell of the invitations row when `bid_invitations.status = 'submitted'`. Same actions cell that currently holds Resend Bid Link / Mark Declined.
- Opens a modal (preferred over a dedicated route — keeps return-to-context flow tight on a page where the PM is comparing rows).
- Modal layout (top to bottom):
  - Header: vendor company name + contact name/email + status pill + total amount (large)
  - Submission metadata: submitted_at timestamp, direct-assign indicator if applicable
  - Line items: clean table matching the structure the vendor saw on the portal's pricing step (description, qty, UoM, unit price, lump sum amount, line total). Sorted by `sort_order`.
  - Vendor notes: rendered as plain text in a bordered panel; hidden if empty.
  - Attachments: list with file name, file size, file type icon, download button (signed URL). Hidden if no attachments.
- Read-only. No edit / annotate / approve / reject actions inside the modal.
- Mobile: modal becomes near-full-screen; line item table scrolls horizontally if columns overflow.
**Out of scope:**
- Cross-bid comparison (Phase 8)
- PM annotations or notes on bids (Phase 8)
- Editing, voiding, or invalidating submitted bids
- Draft visibility / "vendor has a draft in progress" signals (vendor-private)
- "View Bid" action on declined / expired / sent / opened rows (only `submitted` shows the button)
**Acceptance criteria:**
- `GET /v1/bid-submissions/{id}` returns full nested submission shape with signed attachment URLs; 404 if missing; admin-authed.
- "View Bid" button appears in the actions cell of submitted-status invitations rows and nowhere else.
- Modal opens with full submission contents; closes cleanly; works in mobile viewport.
- Skeleton state while submission loads; empty states for "no notes" and "no attachments" handled silently (sections hidden, not shown empty).

---

### Task 6.3: Bid Package List View (~6–8h)

**Goal:** Bid packages currently exist only as nested children of tasks — the only way to find them is to navigate Project → Task → Bid Packages section. As bids accumulate across multiple projects, PMs need a cross-task overview to see all in-flight bidding work in one place.

**New page:** `/bid-packages` (route already-conceivable; sidebar nav addition needed)

**Page layout:**

- Header: "Bid Packages"
- Filter bar:
  - Status filter (chips or dropdown): All / Open / Closed / Evaluating / Cancelled
  - Project filter (dropdown of active projects)
  - Sort: Deadline (default ascending), Created Date, Project Name
- Main table (one row per bid package):
  - Project name (clickable → project detail)
  - Task name (clickable → task detail)
  - Round number (badge — `R1`, `R2`, etc.)
  - Deadline (with countdown — "in 3 days", "passed 2 days ago"). Reuse the existing countdown pattern from `BidPackageDetailPage`.
  - Status badge
  - Submission progress: `{submitted_count} / {total_invitations}` with a small inline bar
  - Created Date (sortable)
  - Click row → navigates to `BidPackageDetailPage`

**Data fetching:**

- New endpoint: `GET /v1/bid-packages` with query params for `status`, `project_id`, `sort_by`, `sort_order`. Returns bid packages with denormalized project/task names and submission counts (compute counts in SQL — don't push that to the client).
- Or, if the team prefers staying in Supabase JS client land: a view or RPC that returns the same denormalized shape. FastAPI is the more consistent choice given Phase 4's pattern.
- Use a single hook `useBidPackagesList(filters)` with React Query.

**Sidebar navigation:**

- Add a new top-level nav item: "Bids" (or "Bid Packages") with an appropriate icon. Position it between "Projects" and "Vendors" or similar — wherever it fits the existing visual flow.

**Empty / loading states:**

- Skeleton rows while loading
- Empty state when no bid packages exist: "No bid packages yet. Start bidding on a task to create one." with a link back to projects.
- Empty state with active filters: "No bid packages match these filters" with a "Clear filters" button.

**Mobile:**

- Table becomes a card list — each card shows project/task as the heading, with deadline + status + progress as bullets below.
- Filter bar collapses into a single "Filters" button that opens a sheet/drawer.

**Out of scope:**
- Bulk actions on bid packages (cancel multiple, etc.) — not needed
- Inline detail expansion — clicking the row goes to the detail page, that's enough

---

### Task 6.4: Charts on Bid Package Detail (~6–7h)

**Goal:** Add two charts to the bid package detail page — a small status pie centered below the stat cards row, and a full bid amount comparison bar chart between the invitations table and email log.

**Library:** Recharts. Add to `frontend/package.json`.

**Chart 1: Submission Status Pie (small, below stat cards)**

- Placement: new row directly below the 4 stat cards, above the Instructions banner. Centered, compact width (roughly the size of two stat cards).
- Acts as a quiet visual accent at small invitation counts (5–10 vendors), becomes the primary scanning tool at larger counts (20+ vendors).
- Slices: sent, opened, submitted, declined, expired. Skip empty slices.
- Reuse the same color palette as the StatusBadge component (sent = blue, opened = yellow, submitted = green, declined = red, expired = gray).
- Tooltip: status name + count + percentage.
- Always rendered when invitations exist. Hidden only if zero invitations (edge case — bid package with no vendors invited yet).

**Chart 2: Bid Amount Comparison Bar (full section)**

- Placement: new section between Invitations table and Email Log, titled "Submitted Bid Amounts."
- Conditionally rendered: only when `submitted_count >= 1`. Section fully hidden when zero submitted.
- Email Log remains the last collapsible section.

**Bar chart shape:**
- Horizontal bars, one per submitted bid, labeled with vendor company name.
- X-axis: `total_amount` formatted as currency.
- Sort ascending — lowest bid at top.
- If `tasks.budget_estimate` is set, vertical dashed reference line labeled "Budget Estimate"; bars exceeding it rendered in a warning color.
- Tooltip: vendor name + formatted amount.

**Data fetching:**
- Pie: uses the existing `invitation_summary` already returned by `GET /v1/bid-packages/{id}`. No backend change.
- Bar: extend the same endpoint response with `submitted_bids` array (vendor company name + total_amount). Single fetch.

**Mobile:**
- Stat cards row stacks to 2-column or single-column.
- Pie chart full-width below the cards.
- Bar chart full-width; X-axis ticks may truncate.

**Out of scope:**
- Score-comparison radar (Phase 8)
- Submission timeline chart
- Export to image / PDF

---

### Task 6.5: Polish — Skeletons, Empty States, Mobile Review (~3–4h)

**Goal:** Catch the visual regressions and rough edges introduced by 6.1–6.4.

**Sub-tasks:**

- **Loading skeletons** for: dashboard stat cards (Task 6.1), Active Projects card (Task 6.2), bid packages list page (Task 6.3), both charts (Task 6.4). Reuse the existing skeleton primitives if they exist; create minimal new ones if needed.
- **Empty states** for the same surfaces, with consistent voice and call-to-action style. Match the tone of existing empty states in the projects/vendors lists.
- **Mobile pass.** Walk through dashboard, bid packages list, bid package detail (with charts) on a phone-width viewport. Adjust layout where things break.
- **Responsive table → card transformations.** Bid packages list specifically — verify the card view on mobile is clean.
- **Loading transitions.** No layout-shift between skeleton and real content. No flash-of-zero before the count loads.

**Out of scope:**
- Animations beyond the existing default transitions
- Dark mode (not in MVP)
- Accessibility audit (Phase 12 territory)

---

## Phase 6 Acceptance Criteria

- [ ] Magic link validation transitions `sent` → `opened` exactly once
- [ ] Lazy `expired` transition applied when PM views a past-deadline bid package
- [ ] "Mark No Response" no longer in the invitations table UI
- [ ] `responded_at` populated when marking declined
- [ ] `PUT /status` rejects overwrites of `submitted` invitations (409)
- [ ] Resend rejects past-deadline attempts (400)
- [ ] Dashboard stat cards all show real data, no `--` placeholders
- [ ] Active Projects card on dashboard, sorted by recent activity, empty state handled
- [ ] Bid Package list page accessible from sidebar, filters and sort working
- [ ] Submission status pie chart displays on bid package detail with correct colors
- [ ] Bid amount comparison bar chart displays once submissions exist; budget reference line if set
- [ ] All new surfaces have skeletons and empty states
- [ ] Mobile layout verified for dashboard, bid packages list, bid package detail with charts
- [ ] No `refetchInterval` added; refresh model unchanged from prior phases
- [ ] No Realtime subscriptions added; existing dormant hooks remain untouched
- [ ] Recharts added to `package.json`; no other charting library introduced

---

## What Phase 6 Intentionally Does NOT Include
 
- **No polling / `refetchInterval`.** The existing `staleTime + refetchOnWindowFocus + mutation invalidation` model is the right design for ≤10 PMs and low-frequency writes.
- **No Supabase Realtime subscriptions.** Existing hooks remain dormant for post-MVP.
- **No completeness checker.** The Phase 5 form prevents incomplete submissions structurally.
- **No timeline / activity feed component.** Phase 10's notifications system will provide cross-project event visibility.
- **No score-comparison radar chart.** Phase 8 owns that work.
- **No draft visibility for PMs.** Drafts are vendor-private; PMs only care about submitted bids.
- **No PM annotations on bids.** Phase 8 territory.
- **No CSV / PDF exports.** Phase 8 / post-MVP.
- **No "Cancel Bid Package" wiring.** The button is a TODO stub; deferred as a separate cleanup.

---

## Next Phase Preview

**Phase 7: Reminder & Alert System (44h)** — n8n workflows for bid reminders (T-7, T-3, T-0), document expiration monitoring (T-30, T-7), tiered email templates, escalation alerts.

**Phase 8: Bid Comparison & Scoring (40h)** — Bid normalization across pricing formats, weighted scoring algorithm (50/5/20/10/15), side-by-side comparison UI with the Recharts foundation from Phase 6.

**Phase 9: Award Decision & Contract Generation (40h)** — Pre-award validation, DocuSign integration, award/decline notifications, direct assign synthetic submission flow.

---

## References

- Full project plan: `docs/PROJECT_PLAN.pdf` (v2.1, 12 phases, ~718h)
- Database schema: `database/bluonx_complete_schema_v2_2.sql`
- RLS policies: `database/rls_policies.sql`
- Storage policies: `database/storage_rls_policies.sql`
- Handoff document: `docs/BluOnX_Context_Handoff.md`
- Deferred tasks: `docs/DEFERRED.md`
