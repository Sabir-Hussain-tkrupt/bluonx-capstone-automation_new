# Current Phase Tasks — BluOnX Development Operations Platform

**Last Updated:** March 11, 2026

---

## Phase 1: Foundation & Database (60h) — ✅ COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| 1.1 — Supabase project setup | ✅ | Free-tier dev account configured |
| 1.2 — Core database schema | ✅ | 28 tables — `database/bluonx_complete_schema_v2_2.sql` |
| 1.3 — Database indexes | ✅ | 49 custom indexes (Section 5 of schema) |
| 1.4 — Row Level Security | ✅ | 28 SELECT + 8 WRITE policies — `database/rls_policies.sql` |
| 1.5 — Database triggers | ✅ | 25 triggers, 11 functions (Section 6 of schema) |
| 1.6 — Storage buckets | ✅ | 3 private buckets, 12 storage RLS policies |
| 1.7 — Auth framework | ✅ | Supabase Auth configured, frontend integration done in Phase 2 |
| 1.8 — Dev/staging environments | ⏳ DEFERRED | Using free-tier dev; prod separation at deployment |
| 1.9 — AWS infrastructure | ⏳ DEFERRED | Pending client AWS credentials |

## Phase 2: Frontend Foundation, Backend API & Auth (100h) — ✅ COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| 2.1 — React + Vite + TailwindCSS v4 | ✅ | Vite + TS, TW4 CSS-first `@theme`, feature-based dirs, `@/` alias |
| 2.2 — Routing (React Router v6) | ✅ | All routes defined, ProtectedRoute, navigation guards |
| 2.3 — Supabase Client + State Mgmt | ✅ | Singleton client, AuthContext/Provider, `onAuthStateChange` (sync fire-and-forget), `fetchProfile` with AbortController timeout |
| 2.4 — React Query API Layer | ✅ | Provider configured, custom hooks pattern (Supabase reads + FastAPI writes), cache invalidation |
| 2.5 — Reusable UI Component Library | ✅ | Inputs, layout, data display, navigation, form components — all TW4 |
| 2.6 — FastAPI Backend Scaffolding | ✅ | Project structure in `backend/`, single Supabase admin client via lifespan, Pydantic v2 models, JWT middleware (PyJWT HS256 audience="authenticated"), CORS, Docker, endpoint scaffolding |
| 2.7 — Authentication System | ✅ | Login/register/reset UI, email/password only, session persistence, ProtectedRoute HOC, role-based rendering |
| 2.8 — Main Dashboard Layout | ✅ | Sidebar + top header + breadcrumbs + user menu, responsive hamburger |
| 2.9 — Responsive Design | ✅ | Mobile 320px+ / tablet 768px+ / desktop 1024px+, touch targets, card views on mobile |

**Deferred from Phase 1 (to be addressed at deployment — see `docs/DEFERRED.md`):**
- Task 1.8 — Dev/staging environment separation
- Task 1.9 — AWS infrastructure setup (pending client credentials)

---

## Phase 3: Core Entity Management — 🔄 IN PROGRESS

**Goal:** Full CRUD interfaces and API endpoints for four core entities (vendors, projects, tasks, bid templates) plus document upload and Google Maps integration. After this phase, PMs can manage all data needed before the bid invitation flow begins.

### Architecture Context (carry forward from Phase 2)

- **Reads:** Supabase JS client (browser) → RLS policies. Authenticated users see non-deleted records automatically.
- **Writes:** All mutations go through FastAPI → single Supabase service_role admin client (bypasses RLS). Never write directly from the browser.
- **FastAPI pattern:** Admin client initialized once at startup via lifespan context manager. Endpoints get it via dependency injection. Pydantic v2 for all request/response models. `created_by` / `uploaded_by` resolved server-side from JWT, never from client payload.
- **Frontend data pattern:** React Query custom hooks. `useQuery` for reads (Supabase client), `useMutation` for writes (Axios → FastAPI). `onSuccess` invalidates relevant query keys.
- **Soft deletes:** `deleted_at` TIMESTAMPTZ on vendors, projects, tasks. Set `deleted_at = NOW()` on delete, never hard-delete. RLS policies already filter `deleted_at IS NULL`.
- **File uploads:** Coat-check pattern — metadata row in DB, file in Supabase Storage bucket. FastAPI handles upload via service_role, returns storage path, inserts metadata row.

---

### Task 3.1 — Vendor Management Interface (15h)

**Tables:** `vendors`, `vendor_contacts`, `vendor_trades`, `vendor_documents`

**Backend endpoints:**
- `GET /v1/vendors` — list with search, sort, filter (status, onboarding_status, trade). Exclude `deleted_at IS NOT NULL`.
- `GET /v1/vendors/{id}` — detail with contacts, trades, documents, flags
- `POST /v1/vendors` — create vendor + contacts + trade associations in one transaction
- `PUT /v1/vendors/{id}` — update vendor fields
- `DELETE /v1/vendors/{id}` — soft delete (`deleted_at = NOW()`)
- `POST /v1/vendors/{id}/contacts` — add contact
- `PUT /v1/vendors/{id}/contacts/{contact_id}` — update contact
- `POST /v1/vendors/{id}/trades` — bulk associate trades (accept array of trade_ids)
- `DELETE /v1/vendors/{id}/trades/{trade_id}` — remove trade association
- `POST /v1/vendors/import` — CSV import

**Frontend components:**
- `VendorListPage` — table with search, filter dropdowns (status, onboarding, trade), sortable columns, pagination
- `VendorDetailPage` — sections: Overview, Contacts, Trades, Documents, Flags/History
- `VendorForm` — create/edit mode with validation
- `VendorCSVImport` — file upload → field mapping UI → validation preview → confirm
- Contacts sub-form: inline add/edit within vendor detail, `is_primary` toggle
- Trade association: multi-select dropdown from `trades` table

**CSV import details:**
- Parse client-side with Papaparse
- Field mapping step: map CSV columns → vendor fields (company_name, address, city, state, zip, contacts)
- Validation preview: show errors/warnings before commit (missing required, duplicates)
- Backend processes rows, creates vendor + contact records, returns success/error summary
- Must handle 100+ rows in one import

**Key constraints:**
- Vendor = company, not person. Contacts are separate child records.
- `onboarding_status` (pending/partial/complete) is PM-managed manually, not auto-computed from docs.
- `latitude`/`longitude` — accept as optional fields now. Actual geocoding wired in Task 3.5.
- `current_active_jobs` — trigger-managed, read-only in UI.
- Vendor flags: read-only display here (creation is Phase 10 Task 10.6). Show existing flags as warning badges.

---

### Task 3.2 — Project Management (12h)

**Tables:** `projects`, `project_documents`

**Backend endpoints:**
- `GET /v1/projects` — list with status filter, search, sort. Exclude deleted.
- `GET /v1/projects/{id}` — detail with tasks, documents, budget summary
- `POST /v1/projects` — create. `created_by` from JWT.
- `PUT /v1/projects/{id}` — update
- `DELETE /v1/projects/{id}` — soft delete
- `GET /v1/projects/{id}/documents` — list documents
- `POST /v1/projects/{id}/documents` — upload (see Task 3.4)
- `DELETE /v1/projects/{id}/documents/{doc_id}` — delete storage file + DB row

**Frontend components:**
- `ProjectListPage` — cards or table with status badges (planning/active/on_hold/completed/cancelled), search, filter
- `ProjectDetailPage` — overview, task list (Task 3.3), documents section, budget tracking
- `ProjectForm` — fields: name, description, address, city, state, zip, budget, status, start_date, estimated_end_date

**Budget tracking display:**
- Show: project budget, sum of task `budget_estimate` values, remaining unallocated
- Warning indicator when task budgets exceed project budget (not blocking)

**Key constraints:**
- `latitude`/`longitude` geocoded from address — defer to Task 3.5, accept as optional now.
- Budget validation (tasks ≤ project) enforced at FastAPI layer, not DB. Warning, not hard block.
- All projects visible to all authenticated users for MVP (no project-level access restriction).
- `created_by` set server-side from JWT, never from client payload.

---

### Task 3.3 — Task Management Within Projects (10h)

**Table:** `tasks`

**Backend endpoints:**
- `GET /v1/projects/{project_id}/tasks` — list for project, sorted by `sort_order`. Exclude deleted.
- `GET /v1/projects/{project_id}/tasks/{id}` — detail
- `POST /v1/projects/{project_id}/tasks` — create. `created_by` from JWT. Validate: trade_id is active, phase valid, bid_type valid.
- `PUT /v1/projects/{project_id}/tasks/{id}` — update. Validate status transitions.
- `DELETE /v1/projects/{project_id}/tasks/{id}` — soft delete. Block if active bids/awards/contracts exist.
- `PUT /v1/projects/{project_id}/tasks/reorder` — bulk `sort_order` update for drag-and-drop

**Frontend components:**
- Task list within `ProjectDetailPage` — sortable with drag-and-drop reorder
- `TaskForm` — fields: name, description, trade (dropdown), phase (dropdown), bid_type (radio/select), budget_estimate
- Status badges with color coding per status

**Trade dropdown filtering (critical):**
- If task phase = `due_diligence` → show trades where `phase IN ('due_diligence', 'both')`
- If task phase = `development` → show trades where `phase IN ('development', 'both')`
- This is a key UX rule from the client — wrong trades must not appear.

**Bid type behavior context:**
- `competitive` → full bid pipeline (Phases 4–8)
- `direct_assign` → PM picks vendor, synthetic submission created later (Phase 9)
- `internal` → budget line only, no vendor involvement, no bids/awards/contracts/milestones
- Phase 3 builds the CRUD only. Status transitions triggered by later phases.

**Status flow:** `draft` → `bidding` → `evaluating` → `awarded` → `in_progress` → `completed`. Also `cancelled` from any state. Enforce valid transitions at API layer.

**Sort order:** Default new tasks to `max(sort_order) + 1`. Reorder via drag-and-drop updates.

**Budget constraint:** Sum of task `budget_estimate` for a project should not exceed `projects.budget`. Enforce at API layer as warning, not hard block.

---

### Task 3.4 — Document Upload Functionality (10h)

**Buckets (created in Phase 1.6):**

| Bucket | Path Pattern | Max Size | Allowed Types |
|--------|-------------|----------|---------------|
| `vendor-documents` | `{vendor_id}/{document_type}/{filename}` | 10MB | PDF, JPEG, PNG |
| `project-documents` | `{project_id}/{filename}` | 50MB | PDF, JPEG, PNG, DWG |
| `bid-attachments` | `{bid_submission_id}/{filename}` | 10MB | PDF, JPEG, PNG |

> `bid-attachments` wired in Phase 5. Build the reusable component now.

**Backend endpoints:**
- `POST /v1/vendors/{id}/documents` — upload vendor doc. Params: `document_type` (w9/insurance_certificate/master_trade_agreement), `expiration_date` (required for insurance_certificate). Validate file type+size. Upload to storage → insert `vendor_documents` row. `uploaded_by` from JWT.
- `POST /v1/projects/{id}/documents` — upload project doc. Same pattern → `project_documents`.
- `GET /v1/vendors/{id}/documents/{doc_id}/url` — signed download URL (Supabase `createSignedUrl`, 1hr expiry)
- `GET /v1/projects/{id}/documents/{doc_id}/url` — same
- `DELETE /v1/vendors/{id}/documents/{doc_id}` — delete storage file + DB row
- `DELETE /v1/projects/{id}/documents/{doc_id}` — same

**File validation at API layer (no ClamAV):**
- Check MIME type against allowed list per bucket
- Check file size against limit
- Validate extension matches MIME type
- Return 422 with specific error on failure

**Frontend components:**
- `FileUpload` — reusable drag-and-drop (React Dropzone or custom). Props: `allowedTypes`, `maxSize`, `onUpload`, `multiple`. Shows progress bar, inline validation errors.
- `DocumentList` — reusable list showing uploaded docs: file name, type, size, uploaded date/by, expiration date, status. Download and delete actions.
- `DocumentPreview` — inline preview for images/PDFs (nice-to-have)

**Vendor document specifics:**
- Three required types: `w9` (no expiration), `insurance_certificate` (requires `expiration_date`, also update `vendors.insurance_expiration_date`), `master_trade_agreement` (no expiration)
- `vendor_documents.status`: `valid` (default on upload), `expired`, `pending_review`. Expiration monitoring (Phase 7 Task 7.6) updates to `expired`.

---

### Task 3.5 — Google Maps Integration for Location (8h)

**Dependency:** Google Maps API key with Geocoding + Distance Matrix APIs enabled. Client dependency — if key unavailable, build with Haversine-only fallback + feature flag.

**Backend services:**
- `geocode_address(address, city, state, zip) → (lat, lng)` — Google Geocoding API. Cache results.
- `calculate_distance(origin_lat, origin_lng, dest_lat, dest_lng) → miles` — Haversine for bulk pre-filter, Distance Matrix for final accurate results
- `filter_vendors_by_distance(project_id, trade_id, radius_miles=75) → list[vendor_ids]` — Step 1: Haversine pre-filter (~100mi generous), Step 2: Distance Matrix on pre-filtered set, Step 3: return within radius

**Integration points:**
- Vendor create/update: re-geocode if address changed → update lat/lng
- Project create/update: re-geocode if address changed → update lat/lng
- Vendor filtering: called during bid invitation flow (Phase 4)

**Frontend components:**
- Map display (Google Maps JS API): vendor pins relative to project location
- 75-mile radius circle overlay from project
- Distance column in vendor list (miles from current project)
- Address autocomplete on forms (Google Places API — nice-to-have)

**Key constraints:**
- 75-mile default radius (client-confirmed), configurable per query
- Distance Matrix costs ~$5/1000 elements — use Haversine for bulk, Distance Matrix for final set only
- If no API key yet: Haversine-only mode behind feature flag, Distance Matrix activated when key provided

---

### Task 3.6: Build Bid Template Management Interface (16h)

**Context:** Bid templates define how vendors submit pricing for a task — either a single lump sum or a structured line-item breakdown. Templates are stored as a reusable library. Each template is **optionally affiliated with a trade** (`trade_id` is nullable). When a PM creates a bid package (Phase 4), they select a template from this library. The selected template determines the vendor bid form structure. This task builds the admin/PM interface for managing this template library.

**Schema (already applied):**
- `bid_templates`: `id`, `trade_id` (nullable FK → trades), `name`, `is_lump_sum`, `created_by`, timestamps
- `bid_template_items`: `id`, `bid_template_id` (FK → bid_templates, CASCADE), `description`, `item_type` ('lump_sum' | 'unit_price'), `unit_of_measure`, `sort_order`
- `bid_packages.bid_template_id`: nullable FK → bid_templates (used in Phase 4, not this task)

**Backend — FastAPI endpoints:**

1. **GET /v1/bid-templates** — List all templates. Support query params: `?trade_id=<uuid>` to filter by trade, `?search=<string>` to search by name. Include `trade` name in response (join). Return item count per template.
2. **GET /v1/bid-templates/{id}** — Get template with all its `bid_template_items` ordered by `sort_order`.
3. **POST /v1/bid-templates** — Create template. Body: `{ name, trade_id (optional/nullable), is_lump_sum, items: [{ description, item_type, unit_of_measure, sort_order }] }`. Accept items inline on create (single API call). `created_by` set from JWT auth context.
4. **PUT /v1/bid-templates/{id}** — Update template metadata (name, trade_id, is_lump_sum). Separate from item management.
5. **DELETE /v1/bid-templates/{id}** — Delete template. Will fail with 409 if referenced by any `bid_packages` (FK RESTRICT). Return clear error message.
6. **POST /v1/bid-templates/{id}/items** — Add a line item to template.
7. **PUT /v1/bid-templates/{id}/items/{item_id}** — Update a line item.
8. **DELETE /v1/bid-templates/{id}/items/{item_id}** — Remove a line item (CASCADE handles FK).
9. **PUT /v1/bid-templates/{id}/items/reorder** — Bulk update sort_order for all items. Body: `{ items: [{ id, sort_order }] }`.

**Validation rules:**
- Template `name` is required, non-empty
- `trade_id` when provided must reference an active trade
- When `is_lump_sum = false`, template must have at least one item
- Item `description` is required
- Item `unit_of_measure` is required when `item_type = 'unit_price'`, nullable when `item_type = 'lump_sum'`

**Frontend — Template List Page** (`/templates` or `/bid-templates`):
- Table/card list showing: template name, associated trade (or "General"), item count, is_lump_sum badge, created date
- Search bar (filters by template name)
- Trade filter dropdown (includes "All Trades" and "General / No Trade" options)
- "Create Template" button → opens create form
- Row click → navigates to template detail/edit page
- Delete button per row with confirmation dialog. Show error toast if template is in use by a bid package.

**Frontend — Template Create/Edit Page** (`/bid-templates/new`, `/bid-templates/{id}/edit`):
- Form fields: Template Name (text input, required), Trade (dropdown with "None — General Purpose" as first option, then active trades alphabetically), Is Lump Sum (toggle switch — when ON, line items section is hidden/disabled)
- **Line Items Section** (visible when is_lump_sum is OFF):
  - Table of existing items: description, item_type (dropdown: lump_sum/unit_price), unit_of_measure (text input, shown only when item_type = unit_price), sort_order
  - "Add Item" button appends a new row
  - Delete icon per row to remove an item
  - Drag-and-drop OR up/down arrow buttons for reordering (updates sort_order)
  - Inline editing — no separate modal for items
- Save button (calls POST on create, PUT on edit + manages items)
- Cancel button → returns to list

**Frontend — Template Preview** (within detail/edit page or as a tab):
- Read-only view mimicking how the vendor bid form will render
- For lump sum: shows a single "Total Amount" field
- For structured: shows the line item table with columns matching what the vendor sees (Description, Type, Unit, Qty input placeholder, Unit Price input placeholder, Line Total placeholder)
- This is a visual preview only — no data entry

**Follows existing patterns from Tasks 3.1–3.5:**
- Use the same FastAPI router pattern (router file under `/routers`, Pydantic v2 models under `/models`)
- Use the same React Query hooks pattern (`useQuery`, `useMutation` with cache invalidation)
- Use the same form validation approach (React Hook Form or existing form library)
- Use the same table/list component pattern established in vendor and project list views
- Use existing UI components (Button, Input, Select, Modal, Table, Card) from the component library (Task 2.2)
- Toast notifications for success/error feedback
- Loading skeletons while data fetches

**Navigation:** Add "Bid Templates" link to the sidebar navigation under an appropriate section.

**NOT in scope for this task:**
- Template selection during bid package creation (that's Phase 4 — Task 4.1/4.6)
- Vendor-facing bid form rendering from template (that's Phase 5 — Task 5.1/5.4)
- Seeding templates from client spreadsheet data (can be done manually or as a follow-up)

---

## Phase 3 Acceptance Criteria

- [ ] Admin can import 100+ vendor records via CSV with field validation
- [ ] Complete CRUD for vendors, projects, tasks, and bid templates
- [ ] Project documents uploaded and accessible via secure signed URLs
- [ ] Vendor documents (W-9, insurance cert, MTA) uploadable with type/size validation
- [ ] Data validation prevents invalid entries (negative budgets, past dates, missing required fields)
- [ ] Task budget sum validated against project budget at API layer (warning, not blocking)
- [ ] Google Maps calculates distances within 75-mile radius (or Haversine fallback if no API key)
- [ ] Vendor filtering by radius works reliably
- [ ] Bid templates configurable per trade (lump sum or structured line items)
- [ ] Template preview shows vendor-facing bid form layout
- [ ] Trade dropdown in task form filtered by task phase (due_diligence/development/both)
- [ ] All forms have error handling and user feedback (loading, validation, success)
- [ ] Soft delete works correctly for vendors, projects, tasks
- [ ] Drag-and-drop reordering for tasks and bid template items

---

## Next Phase Preview

**Phase 4: Bid Invitation System (50h)** — builds directly on Phase 3 entities:
- Intelligent vendor filtering algorithm (trade + distance + insurance + bonding + capacity + flags)
- Professional HTML bid invitation email templates
- AWS SES integration + SNS bounce tracking
- Batch email sending via n8n workflows
- Invitation status tracking on dashboard
- Vendor selection UI (auto-filter → PM review → confirm & send)
- Creates `bid_packages`, `bid_package_documents`, `bid_invitations`, `magic_link_tokens`

**Phase 5: Bid Collection (60h)** — Custom vendor portal with magic link auth, multi-step bid form, draft save, file uploads. Consumes bid templates from Task 3.6.

---

## References

- Full project plan: `docs/PROJECT_PLAN.pdf` (v2.1, 12 phases, ~707h)
- Database schema: `database/bluonx_complete_schema_v2_2.sql`
- RLS policies: `database/rls_policies.sql`
- Storage policies: `database/storage_rls_policies.sql`
- Handoff document: `docs/BluOnX_Context_Handoff.md` (v3.1)
- Deferred tasks: `docs/DEFERRED.md`
