# Phase 2 · Module 2: Project Budget Structure

**Implementation plan (for approval before any code is written)**

| | |
|---|---|
| Project | Financial Automation & Cash Flow Management System (BluOnX / Capstone) |
| Scope | Phase 2, Module 2, Tasks 2.1 – 2.8 (72 h), plus Task 2.0, the deferred Phase 1.6 role-check code (5 h, already budgeted in Phase 1) |
| Builds on | Phase 1 schema v4.0 (applied and verified on the database) |
| Constraints | Existing award / DocuSign / task / project behaviour unchanged. The UI matches the current app exactly (same components, Tailwind tokens, font sizes, layouts). Database changes ship as one more additive, idempotent migration. |
| Status | **Approved (defaults D1–D10) — implemented.** See `database/migrations/20261118_financial_phase2/` and `PHASE2_RUNBOOK.md`. Deviations: budget screens refresh on change / focus instead of realtime push (needs a realtime-publication change); budget reorder is Move up / down (template page uses drag-and-drop). |

---

## 0. TL;DR

- **New Budget tab** on the project page (admins edit, everyone else views). It shows the budget top to bottom in template order with summary cards (budget / committed / spent / remaining / contingency), grouped by section, with land closings, a bid-vs-budget view and CSV / Excel import-export.
- **Standard budget template**, edited by admins in **Settings → Budget Template**. Creating a project budget copies it and turns **every task into a budget line** automatically. New tasks added later appear in the budget on their own, through a database trigger, so nothing is entered twice.
- **Award hook:** award created → line takes the award amount and the difference moves to or from contingency. DocuSign declined / voided → reversed. DocuSign completed → line locked and its dates set from the contract. All of this is added *after* the existing award / DocuSign code and can never break it.
- **Invoices tab** on the project: field managers, PMs, finance and admins upload invoices for internal T&M lines into a new private `finance-documents` bucket, categorise them to a line, and a payment approval request is started. If an invoice is above the line's remaining allowance, the overage automatically becomes a variance funded from contingency.
- **Database:** migration `20261118_financial_phase2`. It adds views for the totals, procedures (create budget, reorder, remove line, categorise invoice), task-to-budget sync triggers, the default template and the storage bucket. It is additive and re-runnable, with the same pre-flight → apply → verify files as Phase 1.
- **Section 11 lists 10 decisions**, each with a recommended default that I will use unless you say otherwise.

---

## 1. What I analysed

| Area | Finding | How Phase 2 uses it |
|---|---|---|
| Backend layout | `routers/*` (thin, auth + HTTP mapping) → `services/*` (business rules, raise `XxxError(status, detail)`) → `models/*` (Pydantic, `BluOnXBase`). Writes use the service_role key; multi-row writes go through RPCs. | New `routers/budgets.py`, `routers/budget_templates.py`, `routers/internal_invoices.py`; `services/budget_service.py`, `budget_template_service.py`, `budget_award_sync.py`, `internal_invoice_service.py`, `budget_import_export.py`; `models/budgets.py`, `models/internal_invoices.py`. |
| Reads | Frontend reads tables and views **directly from Supabase** (RLS). FastAPI is used only for writes (see `routers/holidays.py`). | Budget screens read the new views directly. FastAPI handles writes, the upload, export and import. |
| Auth | `get_current_active_user`, `require_admin` (by `users.role`). There is no multi-role check yet. | Task 2.0 adds `require_roles(...)`, which reads `user_roles`. |
| Errors | DB `PT403/404/409/422` → services map them to HTTP. `core/db_errors.py` is the global 23505 net. | The same mapping for every financial RPC. |
| Tasks | Created in `routers/tasks.py` by `create_task` and `create_default_tasks` (from `task_templates`); soft-deleted; `bid_type` and `budget_estimate` editable. | A task-to-budget-line sync trigger covers both creation paths and any future one. |
| Awards | `award_service.create_award` → `fn_create_award` RPC → post-commit best-effort envelope send. There is no award-cancel endpoint (`DELETE /awards` returns 501). | A post-commit best-effort budget hook after the RPC, using the same pattern as the envelope send. |
| DocuSign | `docusign_webhooks.handle_envelope_event`: `completed` → contract executed and award accepted; `declined/voided` → contract terminated and award `declined_by_vendor`. It has an idempotency guard. | Lock / reverse hooks are added at the end of each branch, wrapped in try/except. |
| Uploads | `core/file_validation.py` (`BUCKET_CONFIGS`, `read_upload`, `validate_upload` with extension / size / signature checks), `core/storage.py` (`upload_file`, `unique_object_path`, `get_signed_url` 1 h, `delete_file`). | A new `finance-documents` entry in `BUCKET_CONFIGS`. The project-documents upload flow is copied. |
| Frontend | React 19 + Vite + TS + Tailwind v4; `components/ui/*` kit (Card, Table, StatCard, Tabs, Modal, FormField, TextInput, Select, DatePicker, FileUpload, DocumentList, StatusBadge, ConfirmDialog, EmptyState, Toast, DropdownMenu); feature folders `api/`, `hooks/`, `components/`, `pages/`; `lib/queryKeys.ts` factory; `useTabParam` tabs; dnd-kit for reorder (TaskList). | A new `features/budgets/` and `features/invoices/` in exactly this structure and with these components only. **No new UI library.** |
| Settings | `pages/SettingsPage.tsx` grid of `SettingsCard`, admin-guarded routes. | A new "Budget Template" card and route. |
| Tests | pytest hermetic by default (`FakeSupabase` in `tests/_fakes.py`); `-m requires_db` for live DB; Vitest + RTL on the frontend. | Unit tests per service and router, live-DB tests for the new procedures, a verify SQL script, and Vitest for the new components. |

---

## 2. Task 2.0: Role checks (deferred Phase 1.6 code, needed now)

Phase 2 is the first phase where non-admins act on financial data (invoice upload), so this lands first.

**Backend (`core/auth.py`):**
- `get_current_active_user` additionally loads the user's active `user_roles` and returns `roles: list[str]` and `is_employee`. Existing keys are unchanged, so every current endpoint keeps working.
- New `require_roles(*roles)` dependency factory. Admin always passes; otherwise the user needs at least one of the listed roles, or gets 403.
- `models/users.py`: `UserInviteRequest` gains optional `roles: list[Literal['field_manager','executive','finance']]` and `is_employee: bool = True`. The invite passes both in the metadata, which the Phase 1 trigger already reads. `UserResponse.role` is untouched.
- `user_service`: list / admin views include `roles` and `is_employee`. A new admin endpoint `PUT /users/{id}/roles` grants and revokes roles, writing `user_roles` and never deleting rows.

**Frontend:**
- `AuthContext`: also reads `user_roles` and exposes `roles` plus `hasRole(...roles)`.
- `ProtectedRoute` gains an optional `requiredRoles` prop. The existing `requiredRole` keeps working unchanged.
- `InviteUserModal`: a "Financial roles" checkbox group and an "External / temporary field manager" toggle, using the existing Checkbox component. The user roster shows role chips with the existing StatusBadge.

---

## 3. Database migration: `20261118_financial_phase2`

Same delivery as Phase 1: `000_preflight` · `001_budget_structure` (BEGIN/COMMIT, idempotent) · `002_verify` (self-checking, rolls back) · `099_rollback`. It is also appended to the master schema, the RLS file and the schema docs. Everything is additive, and no Phase 1 object changes behaviour.

### 3.1 New / changed objects

| Object | Purpose |
|---|---|
| **Default standard template** (insert only if no default template exists) | Sections in order: **Land** (land purchase, earnest money, due diligence) · **Soft costs** (engineering, permits, impact fees, other soft costs) · **Site work / utilities / roads** (activity slots: clearing, grading, sanitary sewer, water + storm, paving) · **Internal** (attorney / T&M) · **Contingency** · **Long-tail** (escrow bond premium, escrow repairs, property tax). Admins then replace it with the client's real layout (dependency D-1). |
| `fn_create_project_budget(project, actor, template?, contingency_pct?)` | Atomic: project `none → draft`; one line per non-activity template row; **one line per live task**, placed at its matching template slot (match order: `task_template_id` → trade → name); contingency line = pct × base (base = all lines except land and contingency). It returns the lines. `PT409` if a budget already exists. |
| `fn_reorder_budget_lines(project, ordered_ids[])` | Rewrites `sort_order` in one transaction. |
| `fn_remove_budget_line(line, actor)` | Soft-deletes a line. Draft: any line except the contingency line. Baselined: only a $0 line with no award, approvals or invoices (otherwise PT409 "use a variance"). The contingency line can never be removed. |
| `fn_categorise_internal_invoice(invoice, line, actor)` | Atomic: links the invoice to an internal T&M line and computes allowance = line budget − other categorised invoices on that line. If the invoice is above the allowance on a baselined budget, the **overage becomes a variance line** (contingency −overage, ledger `invoice_overage`). Then it creates the `payment_approvals` row(s) (`pending`), one for the in-allowance part and one for the variance part, and sets the invoice to `in_approval`. Draft budget: no variance; the overage is returned so the admin can raise the line. |
| Task-to-line sync triggers on `tasks` | **INSERT** (project has a budget): add a line. Draft: amount = `budget_estimate`. Baselined: $0, because the flat rule requires it. **UPDATE of name** → line name follows. **UPDATE of budget_estimate** (draft only, line untouched since creation) → line amount follows. **UPDATE of bid_type** → the line is replaced with the right type (draft, or a $0 line with no award when baselined; otherwise PT409). **Soft delete** → `fn_remove_budget_line` rules (PT409 if the line carries money after baseline). |
| `v_budget_lines` view (`security_invoker`) | One row per live line with the task / trade / vendor / award / contract names plus computed `variance_total` (child variance lines), `committed`, `spent` (approved + sent-to-finance payments), `invoiced`, `remaining = budget − spent`, and `bid_vs_estimate = budget − original_estimate`. All maths is in `NUMERIC`, so it is exact to the cent. |
| `v_project_budget_summary` view | Per project: total budget, approved total, committed, spent, remaining, contingency now / at baseline, land total, contingency base, line count and a `flat_ok` flag. |
| `contingency_ledger.movement_type` | No change (`invoice_overage` already exists from Phase 1). |
| Storage bucket `finance-documents` | Created by the migration when `storage.buckets` exists (`public = false`). **No** storage policies for `authenticated`: files are reachable only through FastAPI and 1-hour signed URLs, which is stricter than the existing buckets on purpose. |

### 3.2 Integration safety in the database
- None of the existing functions (`fn_create_award`, `transition_milestone`, `fn_mark_contract_complete`, …) are modified.
- The task triggers do nothing for projects with `budget_status = 'none'`, which is every project today. That means zero effect until an admin creates a budget.

---

## 4. Task 2.1: Standard budget template (10 h)

**Backend** `routers/budget_templates.py` (admin only):
- `GET /budget-templates/default`;
- `POST/PATCH/DELETE /budget-templates/{id}/lines`;
- `PUT /budget-templates/{id}/lines/order`.

Validation: types and subtypes, contingency at most once, names not blank. Template edits never touch existing `budget_lines`. They are copied at budget creation, and `template_line_id` only records where a line came from.

**Frontend** `features/budget-templates/`:
- page **Settings → Budget Template** (`/settings/budget-template`, admin route);
- a sortable table grouped by section, using the same dnd-kit pattern as `TaskList`;
- an add / edit line modal (Modal + FormField + Select);
- a delete confirmation using ConfirmDialog.

## 5. Task 2.2: Budget line engine linked to tasks (10 h)

- `POST /projects/{id}/budget` (admin) → `fn_create_project_budget`. Contingency % = `projects.contingency_percent` or the settings default (15).
- **All tasks become lines.** competitive / direct_assign → `bid_activity`; internal → `internal_tm`. The task's `budget_estimate` is the starting amount, and template slot order drives the top-to-bottom view.
- New tasks appear automatically (trigger), so **no double entry**.
- **Engineering bid + T&M:** "Add T&M portion" on a line creates an `internal_tm` line under the same section heading (*Engineering*).
- **Lines without a task:** "Add line" (admin) for land, permit, impact fee, soft cost and long-tail.
- **Removing lines:** "Remove" (admin) → `fn_remove_budget_line`, keeping the checklist behaviour.
- **Baseline:** "Baseline budget" (admin, with a confirm dialog explaining that estimates freeze and the total becomes flat) → Phase 1 `fn_baseline_project_budget`.

## 6. Task 2.3: Land lines and phased closings (6 h)

- Land purchase, earnest money and due diligence are separate land lines from the template, `is_payment_exempt = TRUE`, and excluded from the contingency base.
- **Closings panel** (expandable under the land-purchase line): a table of closings with sequence, acres, amount, planned / actual date and status, plus add / edit / cancel (admin).
  - API: `POST/PATCH /budget-lines/{id}/closings`.
  - A warning (not a block) when the sum of closings ≠ land line amount.
- Each closing's date is stored for Phase 8 cash flow.

## 7. Task 2.4: Budget builder interface (14 h)

New **Budget** tab in `ProjectDetailPage`, inserted between Tasks and Documents and using the existing `Tabs` and `useTabParam`.

| State | What the user sees |
|---|---|
| No budget | `EmptyState`. "Create budget from standard template" for admins, "No budget yet" for others. |
| Draft | `Alert info` "Draft budget: amounts can be changed until the budget is baselined", plus the **Baseline budget** button. |
| Baselined | `Alert neutral` explaining that changes now go through bids, variances and top-ups. |

Layout, top to bottom:
1. **Summary cards** (Task 2.7): `StatCard` ×5.
2. **Toolbar**: Add line · Import · Export · view toggle (Lines / Bid vs Budget).
3. **Budget table** (`Table` component), grouped by section with section subtotal rows and a project total row.
   - **Columns:** Line (name + type badge + 🔒 if locked + task link), Budget, Committed, Spent, Remaining, Start, End, Terms, Bucket, Actions.
   - **Editing:** an **Edit line** modal (React Hook Form + Zod) for budget amount (draft only), start date, end date, payment terms and cash bucket.
   - **Validation:** no negative amounts, end ≥ start, both dates required to count in cash flow (otherwise a "dates missing" badge), terms 0–365.
   - Server errors from the guards (`PT409` locked / baselined) are shown in a toast with the database's message.
- **Role behaviour:** admin = all edit controls. Other roles = the same table read-only, with action buttons hidden, not just disabled, mirroring how the existing pages hide admin actions.
- **Archived project:** read-only, like the Tasks and Documents tabs.
- **Data:** `useProjectBudget(projectId)` reads `v_budget_lines` and `v_project_budget_summary` through Supabase. Mutations call FastAPI and invalidate the `queryKeys.budgets.*` keys. Realtime invalidation reuses the existing `useRealtimeQueryInvalidation` on `budget_lines`, so awards arriving from another user show up live.
- **Look & feel:** only existing `components/ui` parts, the existing heading sizes (`text-xl/2xl` page, `text-base font-semibold` section headers, `text-sm` body, `tabular-nums` money), the `secondary-*` / `primary-*` tokens, and `formatCurrency` / `formatDateOnly` from `lib/format`. **No new colours, fonts or component library.**

## 8. Task 2.5: Hook bid awards into budget lines (10 h)

New `services/budget_award_sync.py`. Every function is **best-effort, post-commit, idempotent and logged**. An exception is caught and logged, and it **never changes the existing response or behaviour**.

| Existing event | Hook added after the existing code | Procedure |
|---|---|---|
| `award_service.create_award` after `fn_create_award` succeeds | `apply_award(award)`: if the task has a live budget line → apply | `fn_apply_bid_to_line` (difference ↔ contingency on a baselined budget; line only on a draft) |
| DocuSign `declined` / `voided` branch | `reverse_award(award)` | `fn_reverse_bid_on_line` |
| DocuSign `completed` branch | `lock_for_contract(contract)` | `fn_lock_budget_line` (lock + default dates from the contract) |

- **Safety net, `POST /projects/{id}/budget/sync-awards` (admin, plus a "Sync awards" menu item):** re-applies any active award not yet on its line and locks any line whose contract is executed. All procedures are idempotent, so running it repeatedly is harmless. It covers a hook that failed, and awards that existed before the budget was created (back-fill).
- **Reused, not rebuilt:** the existing award email and DocuSign contract remain the award notice and PO.
- **Tests:** every existing award and DocuSign test must pass unchanged, plus new tests that (a) the hook runs, (b) a hook exception does not change the award / webhook result, and (c) idempotency on webhook retries.

## 9. Task 2.6: Internal invoice intake (10 h)

- **Who can upload:** `require_roles('field_manager','finance','project_manager')` (admins always). See D10.
- **API (`routers/internal_invoices.py`):**
  - `POST /projects/{id}/invoices` (multipart file + payee / vendor, number, date, amount): the same `read_upload` → `validate_upload` → `upload_file` → insert flow as project documents, with bucket `finance-documents` added to `BUCKET_CONFIGS` (PDF / images / office docs, 25 MB);
  - `GET /invoices/{id}/url`: 1 h signed URL;
  - `PATCH /invoices/{id}`: edit details while `received`;
  - `POST /invoices/{id}/categorise {budget_line_id}` → `fn_categorise_internal_invoice`;
  - `POST /invoices/{id}/cancel`.
- **Payment approval workflow start:** categorisation creates `payment_approvals` rows in `pending`. The approve / route / reject actions are Phase 6. Phase 2 shows the request and its status only.
- **Frontend: new Invoices tab** on the project.
  - A table of invoices (StatusBadge for status, line, amount, uploaded by, date).
  - An upload modal (existing `FileUpload` + form).
  - A categorise modal (Select of internal T&M lines with their remaining allowance).
  - **Overage preview:** "This invoice is $1,200 over the line's remaining $800. A $400 variance will be funded from contingency".
  - Download via signed URL.
  - Finance-restricted reads: RLS already limits `internal_invoices` to finance / executive / admin. Field managers and PMs see **the invoices they uploaded**: the server returns those through `GET /projects/{id}/invoices`, which filters by role, because RLS cannot express "own rows" for them without exposing all invoices.

## 10. Tasks 2.7 & 2.8: Summary, import / export (12 h)

**2.7 Summary (6 h):**
- **Cards:** Total budget · Committed · Spent · Remaining · Contingency (now / at baseline, with a warning accent when below 50% of baseline).
- **Bid vs Budget view:** per activity, original estimate → awarded → variance → difference ($ and %) as a table, plus a Recharts horizontal bar chart (estimate vs committed). It uses the chart styling already used on the dashboard (Recharts is already a dependency).
- **Spent vs committed** columns.

**2.8 Import / export (6 h):**
- **Export:** `GET /projects/{id}/budget/export?format=xlsx|csv` (any active user). Built with **openpyxl** (new backend dependency, already in the project plan). Sections, lines, all money columns, dates, terms and bucket, plus a totals row. Money is written as numeric cells with a `$#,##0.00` format.
- **Import:** draft budgets only, admin.
  - `POST /projects/{id}/budget/import/preview` (CSV or XLSX upload) → parsed rows, matched to existing lines by name (case-insensitive), with unmatched rows proposed as new lines and per-row validation errors.
  - `POST …/import/apply` with the confirmed rows → updates amounts / dates / terms / bucket and adds lines in one RPC.
  - **Columns:** Section, Line, Type, Amount, Start, End, Payment terms, Cash bucket, with header aliases ("Budget", "Cost", "Description"…).
  - Parsed **server-side** for both formats, so CSV and Excel follow one code path (see D5).
- **UI:** an Import modal with a file drop → preview table (row status badges) → "Apply N changes".

---

## 11. Decisions (recommended defaults in **bold**)

| # | Decision | Recommended |
|---|---|---|
| D1 | How new tasks reach the budget | **DB trigger on `tasks`.** It covers `create_task`, `create_default_tasks` and any future path with no code duplication. (Alternative: Python calls in every task endpoint.) |
| D2 | Award hook | **Post-commit, best-effort, idempotent Python hook + "Sync awards" safety net.** `fn_create_award` is not modified, so award creation can never fail because of the budget. |
| D3 | Lines after baseline | **New lines start at $0. Removal only for $0 lines without award / invoices / approvals.** Funding a forgotten line after baseline goes through variances (Phase 4). This keeps the flat rule and "savings can't move to another line" (Phase 3). |
| D4 | Template activity rows | **Ordering slots matched to tasks.** Activity lines exist only as tasks; the template decides their position and heading. |
| D5 | Import parsing | **Server-side (openpyxl + csv) for both formats.** One validator, and an Excel parser isn't needed in the browser. PapaParse stays unused for this feature. |
| D6 | Phase 1.6 role code | **Build it now as Task 2.0** (needed for invoice upload by non-admins). |
| D7 | "Spent" | **Payments approved or sent to finance** (Phase 6 fills it; $0 until then). Invoices create *pending* approval requests now. |
| D8 | Legacy `projects.budget` | **Untouched** (still shown on Overview, still admin-editable). The financial total lives in the Budget tab. |
| D9 | Baseline action in Phase 2 | **Yes, the admin "Baseline budget" button.** It is needed so awards move contingency. |
| D10 | Who uploads invoices | **field_manager, finance, project_manager, admin** ("office staff" = PMs / admins). External field managers can upload too, as they hold `field_manager`; they still can never authorise payment (Phase 6). |

---

## 12. Files that will be created / changed

```
database/migrations/20261118_financial_phase2/   000 · 001 · 002 · 099 · README
database/bluonx_complete_schema.sql · rls_policies.sql · bluonx_schema_documentation.md   (appended)
database/seed_data/dev_seed_financial_phase2.sql  (dev: template-driven budget on a demo project, invoices)

backend/app/core/auth.py                     roles + require_roles            (Task 2.0)
backend/app/core/file_validation.py          + finance-documents bucket
backend/app/models/{users,budgets,budget_templates,internal_invoices}.py
backend/app/routers/{users,budgets,budget_templates,internal_invoices}.py
backend/app/services/{user_service,budget_service,budget_template_service,
                      budget_award_sync,internal_invoice_service,budget_import_export}.py
backend/app/services/award_service.py        + 1 hook call after fn_create_award
backend/app/routers/docusign_webhooks.py     + 1 hook call per branch
backend/app/routers/tasks.py                 map PT409 from the sync trigger on delete / update
backend/app/main.py                          register 3 routers
backend/requirements.txt                     + openpyxl
backend/tests/{auth_roles,budgets,budget_templates,budget_award_sync,internal_invoices,budget_import_export}/

frontend/src/contexts/AuthContext.tsx, components/auth/ProtectedRoute.tsx    roles   (Task 2.0)
frontend/src/features/user-management/…      roles in invite + roster              (Task 2.0)
frontend/src/features/budgets/               api · hooks · components · __tests__
frontend/src/features/budget-templates/      settings page
frontend/src/features/invoices/              Invoices tab
frontend/src/features/projects/pages/ProjectDetailPage.tsx   + Budget, Invoices tabs
frontend/src/pages/SettingsPage.tsx, routes/index.tsx, constants/{routes,api}.ts, lib/queryKeys.ts

docs/financial/PHASE2_RUNBOOK.md
```

---

## 13. Implementation order & verification

| Step | Work | How I verify it |
|---|---|---|
| 1 | DB migration + verify script | Local Postgres 15 with v3.9 + Phase 1: apply twice, verify all PASS, rollback → identical schema |
| 2 | Task 2.0 roles | Unit tests; all existing user / auth tests unchanged |
| 3 | Template + budget engine + land closings (2.1–2.3) | Service / router unit tests (FakeSupabase), live-DB tests (`requires_db`) for the procedures and triggers |
| 4 | Award hooks (2.5) | Existing award + DocuSign suites green, plus new hook / idempotency tests |
| 5 | Invoices (2.6) | Upload validation, categorise, overage-variance tests |
| 6 | Import / export (2.8) | Round-trip test: export → import gives zero changes; cent-exact totals |
| 7 | Frontend (2.4, 2.6, 2.7, templates, roles) | Vitest + RTL component tests, `npm run lint`, `tsc -b`, `npm run build`; visual check in the browser against existing pages |
| 8 | Docs + runbook | — |

Full regression: the whole hermetic backend suite (`pytest`) and the frontend suite (`npm test`) must pass, as before.

---

## 14. Acceptance criteria → proof

| Criterion | Proof |
|---|---|
| New budgets start from the standard template and can be adjusted | `fn_create_project_budget` live test; UI add / remove / reorder / edit |
| Every existing and new task appears as a line, without double entry; unneeded lines removable | Live tests: budget creation over N tasks = N activity lines; new task → line (trigger); remove line |
| Land shows purchase / earnest / due diligence separately, any number of phased closings | Template + closings API tests; UI panel |
| Only admins create / edit budgets | `require_admin` on every budget write; router tests for 403 as PM / field manager / finance |
| Land / permit / impact fee / long-tail lines without a task | Add-line tests |
| Every line stores start, end, terms, bucket | Edit-line tests; schema already enforces it |
| Award updates line + contingency; decline reverses | Hook tests + live procedure tests (ledger rows) |
| Lines lock when the contract is executed | Webhook `completed` hook test |
| Existing award and DocuSign behaviour unchanged | The existing test suites pass untouched; hook-failure tests |
| Invoices uploaded, categorised, sent for approval; overage → variance | Invoice service + live procedure tests |
| Totals accurate to the cent | NUMERIC-only views; property test with many fractional amounts; export → import round-trip |

---

## 15. Risks

| Risk | Mitigation |
|---|---|
| A task trigger surprises existing task flows | It is a no-op for projects without a budget (all projects today). PT409 only when deleting a task whose baselined line carries money, mapped to a clear 409 in `tasks.py`. |
| A hook failure hides a budget mismatch | Logged with the award id, plus the "Sync awards" safety net. Phase 5's health sweep can later run the same sync daily. |
| Client's real template / Excel layout unknown | The default template ships now; admins edit it in Settings. Import header aliases are configurable. A client sample is needed (D-1). |
| Spent is $0 until Phase 6 | Stated in a card tooltip ("approved payments, from Phase 6"). |

## 16. Client dependencies

- D-1: the client's standard budget layout (all line items in order) and one or two current Excel budgets for the import mapping.
- D-2: confirmation of who uploads invoices (D10) and the allowed invoice file types / size.

---

**Next step:** reply *"approved"*, optionally with changes to D1–D10. I will then implement it in the order of section 13, test it locally, and give you the Phase 2 runbook for applying the migration.
