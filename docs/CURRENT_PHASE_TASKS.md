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

**Goal:** Give PMs real visibility surfaces — a proper landing dashboard, a cross-task bid package overview, and visual breakdowns of in-flight bids.

**Tables read:** `bid_packages`, `bid_invitations`, `bid_submissions`, `bid_line_items`, `tasks`, `projects`, `vendors`, `magic_link_tokens`


### Architecture Context (carry forward from prior phases)

- **Refresh model — intentional, no changes.** Reads use the existing global QueryClient defaults: `staleTime: 2min`, `refetchOnWindowFocus: true`, `refetchOnMount: true`, `refetchOnReconnect: 'always'`. Mutations invalidate query keys in `onSuccess`. **No polling (`refetchInterval`) and no Supabase Realtime subscriptions are added in Phase 6.** The existing `useRealtimeSubscription` and `useRealtimeQueryInvalidation` hooks remain in the codebase but unused — they are intentional dormant infrastructure for post-MVP if needed.
- **Why no real-time?** The current event-driven refresh (focus + interaction + invalidation) covers the actual PM workflow for a small (≤10) team with low write frequency. Bid submissions arrive over days, not seconds. Adding polling or WebSockets would be net-negative — extra load and complexity for no perceived UX gain.
- **Reads:** Continue using Supabase JS client with RLS for authenticated dashboard reads. Writes via FastAPI (service_role).
- **Routing:** All new pages live under the existing admin layout and are wrapped by the standard `ProtectedRoute`. No new role-based gating in Phase 6 — both `admin` and `project_manager` see the same dashboard and bid package list.
- **Charts library:** Recharts. To be added to `frontend/package.json` in Task 6.4. Declarative JSX-based, SVG output, plays well with TailwindCSS theme tokens.


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

### Task 6.2: Bid Package List View (~6–8h)

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

### Task 6.3: Charts on Bid Package Detail Page (~6–8h)

**Goal:** Add two visual breakdowns to the existing Bid Package Detail Page. The summary cards already show counts; charts add comparative shape.

**Library:** Recharts. Add to `frontend/package.json`. No global config needed.

**Chart 1: Submission Status Pie**

- Placement: Right column or top-of-page panel on the bid package detail layout — wherever fits cleanly alongside the existing four summary cards. Could replace one of the cards if the design works better that way.
- Data: same `invitation_summary` object already returned by `GET /v1/bid-packages/{id}` — no new endpoint. Slices: `sent`, `opened`, `submitted`, `declined`, `expired`. Skip `no_response` (now UI-suppressed per Task 0).
- Color tokens: reuse the same palette already used by the `StatusBadge` component to keep visual consistency. Sent = blue, opened = yellow, submitted = green, declined = red, expired = gray.
- Tooltip on hover: status name + count + percentage.
- Empty state: if all counts are zero (shouldn't happen post-invitation-send), show a placeholder rather than an empty pie.

**Chart 2: Bid Amount Comparison Bar**

- Placement: New section below the invitations table, titled "Bid Amounts" or "Submitted Bids."
- Data: pull `bid_submissions` rows for this bid package where `status = 'submitted'`. Need a new endpoint or extend the existing detail response to include submitted bid totals. Recommend extending the detail response — keeps the page on one fetch.
- Chart shape: horizontal bar chart, one bar per submitted bid, labeled with vendor company name. X-axis is `total_amount` formatted as currency.
- If `tasks.budget_estimate` is set, draw a vertical reference line at that value labeled "Budget Estimate."
- Sort bars by amount ascending (lowest bid at top — visually leads the eye to the likely winner).
- Empty state: if no bids submitted yet, show a message: "No bids submitted yet. Bar chart will appear once vendors submit bids."

**Chart placement and responsive behavior:**

- Desktop: pie chart in the upper-right of the page (next to or replacing the summary cards row), bar chart full-width below the invitations table.
- Mobile: both charts stack vertically full-width. Pie chart fixed aspect ratio; bar chart scrolls horizontally if vendor names are long.

**Sub-task notes:**
- Pull this work in only after Task 0 is complete. Otherwise the pie chart is permanently a two-slice chart (sent + submitted only).
- Do not generalize charts into a shared "Chart" component yet. Keep them feature-local in `frontend/src/features/bids/components/`. Generalize only if Task 6.5 polish reveals overlap.

**Out of scope:**
- Score-comparison radar chart (Phase 8 — proper bid comparison)
- Submission timeline chart (added value unclear; status badges + timestamps in the table already convey this)
- Export to image / PDF (Phase 8 / post-MVP)

---

### Task 6.4: Polish — Skeletons, Empty States, Mobile Review (~3–4h)

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

- **No polling / `refetchInterval`.** The existing `staleTime + refetchOnWindowFocus + mutation invalidation` model is the right design for ≤10 PMs and low-frequency writes. Adding polling would be net-negative.
- **No Supabase Realtime subscriptions.** Existing hooks (`useRealtimeSubscription`, `useRealtimeQueryInvalidation`) remain in the codebase as dormant infrastructure for post-MVP. No tables added to `supabase_realtime` publication in this phase.
- **No completeness checker.** The Phase 5 form prevents incomplete submissions structurally — there's no incomplete state to detect post-submission.
- **No timeline / activity feed component.** Phase 10's notifications system will provide cross-project event visibility. Building a parallel activity feed now would duplicate that work.
- **No score-comparison radar chart.** Phase 8 (Bid Comparison & Scoring) owns that work.
- **No CSV / PDF exports.** Phase 8 / post-MVP.
- **No fix for the resend token invalidation bug.** Documented in `docs/DEFERRED.md`. Out of scope for Phase 6.

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
