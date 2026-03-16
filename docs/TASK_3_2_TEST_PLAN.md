# Task 3.2 — Project Management Test Plan

This document contains two test packages:
- **Package A**: End-to-end frontend + backend tests (run from the browser UI)
- **Package B**: Backend-only API tests (run via FastAPI docs or curl)

**Prerequisites:**
- Backend running: `cd backend && uvicorn app.main:app --reload --port 8000`
- Frontend running: `cd frontend && npm run dev`
- Logged in as admin user (e.g., awaisontest@gmail.com)
- Seed data loaded (6 projects exist in DB)

---

## Package A: End-to-End Frontend + Backend Tests

### A1. Dashboard Stats
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A1.1 | Active Projects count | Navigate to `/dashboard` | "Active Projects" card shows a number (e.g., 2), not "--" |
| A1.2 | Active Vendors count | Navigate to `/dashboard` | "Active Vendors" card shows a number (e.g., 43), not "--" |
| A1.3 | Placeholder stats | Check "Open Tasks" and "Pending Bids" | Both still show "--" (not yet implemented) |

### A2. Project List Page — Initial Load
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A2.1 | Page loads | Navigate to `/projects` | Page loads with table of projects, no errors |
| A2.2 | Seed data visible | Check the table | All 6 seed projects are visible |
| A2.3 | Column headers | Check table headers | Columns: Project Name, Location, Status, Budget, Start Date |
| A2.4 | Status badges | Look at Status column | Each status has a colored badge (Active=green, Planning=blue, On Hold=yellow, Completed=gray, Cancelled=red) |
| A2.5 | Budget formatting | Check Budget column | Numbers formatted as currency (e.g., "$1,500,000.00"), right-aligned |
| A2.6 | Date formatting | Check Start Date column | Dates in readable format (not raw ISO) |
| A2.7 | Pagination info | Check bottom of table | Shows "Showing X to Y of Z results" |

### A3. Project List — Search
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A3.1 | Search by name | Type a project name (or part of it) in search box | Table filters to matching projects within ~300ms |
| A3.2 | Search no results | Type "xyznonexistent" in search box | Empty state shown with "No projects found" message |
| A3.3 | Clear search | Clear the search input | Full list returns |
| A3.4 | Partial match | Type first 3 letters of a project name | Matching projects appear |

### A4. Project List — Status Filter
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A4.1 | Filter by Active | Select "Active" from status dropdown | Only projects with Active status shown |
| A4.2 | Filter by Planning | Select "Planning" from status dropdown | Only projects with Planning status shown |
| A4.3 | Filter by On Hold | Select "On Hold" from status dropdown | Only On Hold projects shown |
| A4.4 | Filter by Completed | Select "Completed" | Only Completed projects shown |
| A4.5 | Filter by Cancelled | Select "Cancelled" | Only Cancelled projects shown |
| A4.6 | Clear filter | Select "All Statuses" | Full list returns |
| A4.7 | Filter + search combined | Set status filter AND type in search | Results match both criteria |

### A5. Project List — Sorting
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A5.1 | Sort by name ascending | Click "Project Name" column header | Projects sorted A-Z by name |
| A5.2 | Sort by name descending | Click "Project Name" header again | Projects sorted Z-A by name |
| A5.3 | Sort by status | Click "Status" column header | Projects sorted by status |
| A5.4 | Sort by budget | Click "Budget" column header | Projects sorted by budget amount |
| A5.5 | Sort by start date | Click "Start Date" column header | Projects sorted by date |
| A5.6 | Sort persists with filter | Apply a sort, then apply a search | Sort order maintained after filtering |

### A6. Create Project — Happy Path
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A6.1 | Open form | Click "+ New Project" button | Modal form opens with title "New Project" |
| A6.2 | Form sections | Check the modal | Three sections visible: Project Information, Location, Status & Schedule |
| A6.3 | Default status | Check Status dropdown | Defaults to "Planning" |
| A6.4 | Create minimal project | Enter only "Test Project Alpha" as name, click "Create Project" | Project created, modal closes, toast success message, project appears in list |
| A6.5 | Create full project | Fill all fields: Name="Full Test Project", Description="A detailed project", Address="123 Main St", City="Springfield", State="IL", ZIP="62701", Status="Active", Budget=500000, Start Date=2026-04-01, End Date=2026-12-31 | Project created with all fields saved correctly |
| A6.6 | Verify in list | After creating | New project appears in the project list |
| A6.7 | List count updated | After creating an Active project | Dashboard "Active Projects" count should increase by 1 on next visit |

### A7. Create Project — Validation
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A7.1 | Empty name | Leave name blank, click Create | Error: "Project name is required (min 2 characters)" |
| A7.2 | Name too short | Enter "A" as name, click Create | Error: "Project name is required (min 2 characters)" |
| A7.3 | Negative budget | Enter -100 as budget | Error: "Budget must be >= 0" |
| A7.4 | End date before start | Set start date 2026-12-01, end date 2026-01-01 | Error: "End date must be on or after start date" |
| A7.5 | Cancel button | Fill some fields, click Cancel | Modal closes, no project created, form data cleared |
| A7.6 | Close modal (X) | Fill some fields, click X button | Modal closes, no project created |

### A8. Project Detail Page
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A8.1 | Navigate to detail | Click a project row in the list | Navigates to `/projects/:id` detail page |
| A8.2 | Project header | Check header section | Shows project name, status badge, Edit and Delete buttons |
| A8.3 | Back button | Click back arrow / "Back to Projects" | Returns to `/projects` list |
| A8.4 | Overview tab - Location | Check Overview tab | Shows Address, City, State, ZIP (or "—" if empty) |
| A8.5 | Overview tab - Budget | Check Budget & Schedule section | Shows Budget (formatted), Start Date, Est. End Date |
| A8.6 | Overview tab - Description | Check Description area | Shows project description (if set), otherwise not shown |
| A8.7 | Tabs present | Check tab bar | Three tabs: Overview (active by default), Tasks, Documents |
| A8.8 | Tasks tab placeholder | Click "Tasks" tab | Shows placeholder message for future implementation |
| A8.9 | Documents tab placeholder | Click "Documents" tab | Shows placeholder message for future implementation |

### A9. Edit Project
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A9.1 | Open edit form | On detail page, click "Edit" button | Modal opens with title "Edit Project", pre-filled with current values |
| A9.2 | Verify pre-fill | Check all fields | All fields match the current project data |
| A9.3 | Edit name | Change name to "Updated Project Name", save | Name updates, toast success, detail page reflects new name |
| A9.4 | Edit status | Change status from Planning to Active, save | Status badge updates on detail page |
| A9.5 | Edit budget | Change budget to 999999, save | Budget displays updated value |
| A9.6 | Add description | Add a description where none existed, save | Description now appears in Overview |
| A9.7 | Clear optional field | Remove the city value, save | City shows "—" on detail page |
| A9.8 | Edit date validation | Set end date before start date, try to save | Validation error prevents save |
| A9.9 | Cancel edit | Make changes, click Cancel | Modal closes, no changes saved |

### A10. Delete Project
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A10.1 | Delete button | On detail page, click "Delete" button | Confirmation modal appears |
| A10.2 | Confirm delete | Click "Delete" in confirmation modal | Project deleted (soft delete), redirected to `/projects` list, toast success |
| A10.3 | Deleted project gone | Check the project list | Deleted project no longer appears |
| A10.4 | Cancel delete | Click "Cancel" in confirmation modal | Modal closes, project still exists |

### A11. Navigation & Integration
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A11.1 | Quick Access card | On Dashboard, click "Projects" card | Navigates to `/projects` |
| A11.2 | Sidebar link | Click "Projects" in sidebar | Navigates to `/projects` |
| A11.3 | Direct URL | Navigate to `/projects` directly in browser | Page loads correctly |
| A11.4 | Direct detail URL | Navigate to `/projects/<valid-uuid>` directly | Detail page loads correctly |
| A11.5 | Invalid project ID | Navigate to `/projects/invalid-uuid-here` | Shows error state (not found) |
| A11.6 | Browser back/forward | Navigate list → detail → back | Navigation history works correctly |

### A12. Edge Cases
| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| A12.1 | Very long project name | Create project with 200-character name | Handled gracefully, name truncates or wraps in table |
| A12.2 | Special characters in name | Create project named "Test & <Project> 'Quotes' \"Double\"" | Characters handled correctly, no XSS |
| A12.3 | Zero budget | Create project with budget = 0 | Shows "$0.00" in list and detail |
| A12.4 | Very large budget | Create project with budget = 999999999.99 | Formatted correctly |
| A12.5 | No start date with end date | Set only end date, no start date | Allowed (no cross-validation needed when start is empty) |
| A12.6 | Rapid search typing | Type quickly in search box | Debounce prevents excessive API calls, final results correct |
| A12.7 | Multiple creates | Create 3 projects in quick succession | All 3 appear in the list, no duplicate requests |
| A12.8 | Create then edit immediately | Create a project, click into it, immediately edit | Edit form pre-fills correctly with just-created data |

---

## Package B: Backend-Only API Tests (FastAPI Docs / curl)

**Base URL:** `http://localhost:8000/api/v1`

**Authentication:** All endpoints require a Bearer token. Get one by logging in via Supabase:
```bash
# Get auth token (replace with your credentials)
TOKEN=$(curl -s -X POST 'https://<YOUR_SUPABASE_URL>/auth/v1/token?grant_type=password' \
  -H 'apikey: <YOUR_ANON_KEY>' \
  -H 'Content-Type: application/json' \
  -d '{"email":"awaisontest@gmail.com","password":"awais@tkrupt"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Or use FastAPI docs at http://localhost:8000/docs — click "Authorize" and paste the token
```

### B1. List Projects — GET /projects

```bash
# B1.1 — List all projects (default pagination)
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects" | python -m json.tool
# Expected: { items: [...], total: 6, page: 1, page_size: 25 }

# B1.2 — Pagination
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?page=1&page_size=2" | python -m json.tool
# Expected: 2 items returned, total still = 6, page = 1, page_size = 2

# B1.3 — Page 2
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?page=2&page_size=2" | python -m json.tool
# Expected: Next 2 items, page = 2

# B1.4 — Search by name
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?search=sunset" | python -m json.tool
# Expected: Only projects with "sunset" in the name (case-insensitive)

# B1.5 — Filter by status
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?status=active" | python -m json.tool
# Expected: Only active projects

# B1.6 — Sort by budget descending
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?sort_by=budget&sort_dir=desc" | python -m json.tool
# Expected: Projects sorted by budget, highest first

# B1.7 — Sort by name ascending (default)
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?sort_by=name&sort_dir=asc" | python -m json.tool
# Expected: Projects sorted A-Z by name

# B1.8 — Combined: search + status + sort + pagination
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?search=park&status=planning&sort_by=created_at&sort_dir=desc&page=1&page_size=10" | python -m json.tool
# Expected: Filtered, sorted, paginated results

# B1.9 — Invalid sort column
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?sort_by=invalid_column" | python -m json.tool
# Expected: Falls back to default sort (name) — no error

# B1.10 — Empty result
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?search=xyznonexistent" | python -m json.tool
# Expected: { items: [], total: 0, page: 1, page_size: 25 }

# B1.11 — No auth token
curl -s "$BASE_URL/projects"
# Expected: 401 Unauthorized
```

### B2. Get Project by ID — GET /projects/{id}

```bash
# B2.1 — Get a valid project
# First, get a project ID from the list
PROJECT_ID=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?page_size=1" | python -c "import sys,json; print(json.load(sys.stdin)['items'][0]['id'])")

curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects/$PROJECT_ID" | python -m json.tool
# Expected: Full project object with all fields

# B2.2 — Invalid UUID format
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects/not-a-uuid" | python -m json.tool
# Expected: 422 Validation Error

# B2.3 — Non-existent UUID
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects/00000000-0000-0000-0000-000000000000" | python -m json.tool
# Expected: 404 Not Found

# B2.4 — No auth
curl -s "$BASE_URL/projects/$PROJECT_ID"
# Expected: 401 Unauthorized
```

### B3. Create Project — POST /projects

```bash
# B3.1 — Minimal create (name only)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "API Test Project Minimal"}' \
  "$BASE_URL/projects" | python -m json.tool
# Expected: 201 Created, returns project with status=planning, created_by=<your user id>

# B3.2 — Full create (all fields)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "API Full Test Project",
    "description": "Comprehensive test with all fields populated",
    "address": "456 Oak Avenue",
    "city": "Chicago",
    "state": "IL",
    "zip_code": "60601",
    "budget": 2500000.50,
    "status": "active",
    "start_date": "2026-04-01",
    "estimated_end_date": "2027-03-31"
  }' \
  "$BASE_URL/projects" | python -m json.tool
# Expected: 201 Created with all fields set, created_by from JWT (not from payload)

# B3.3 — Missing required field (name)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"description": "No name provided"}' \
  "$BASE_URL/projects" | python -m json.tool
# Expected: 422 Validation Error — name is required

# B3.4 — Empty name
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": ""}' \
  "$BASE_URL/projects" | python -m json.tool
# Expected: 422 Validation Error — name cannot be empty (min_length=1)

# B3.5 — Invalid status value
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Bad Status Project", "status": "invalid_status"}' \
  "$BASE_URL/projects" | python -m json.tool
# Expected: 422 Validation Error — status must be one of the valid enum values

# B3.6 — Negative budget
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Negative Budget Project", "budget": -5000}' \
  "$BASE_URL/projects" | python -m json.tool
# Expected: 422 Validation Error — budget must be >= 0

# B3.7 — Attempt to set created_by (should be ignored)
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Sneaky Project", "created_by": "00000000-0000-0000-0000-000000000000"}' \
  "$BASE_URL/projects" | python -m json.tool
# Expected: 201 Created, but created_by = YOUR user id (not the one in payload)

# B3.8 — No auth
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"name": "Unauthorized"}' \
  "$BASE_URL/projects"
# Expected: 401 Unauthorized

# B3.9 — Budget with decimals
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Decimal Budget", "budget": 1234567.89}' \
  "$BASE_URL/projects" | python -m json.tool
# Expected: 201 Created, budget = 1234567.89
```

### B4. Update Project — PATCH /projects/{id}

```bash
# Use the PROJECT_ID from B2.1, or get a new one

# B4.1 — Update name only
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Renamed Project"}' \
  "$BASE_URL/projects/$PROJECT_ID" | python -m json.tool
# Expected: 200 OK, name updated, all other fields unchanged

# B4.2 — Update multiple fields
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "on_hold", "budget": 999999.99, "city": "New York"}' \
  "$BASE_URL/projects/$PROJECT_ID" | python -m json.tool
# Expected: 200 OK, all three fields updated, others unchanged

# B4.3 — Update status to completed
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "completed"}' \
  "$BASE_URL/projects/$PROJECT_ID" | python -m json.tool
# Expected: 200 OK, status = completed

# B4.4 — Set optional field to null
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"description": null}' \
  "$BASE_URL/projects/$PROJECT_ID" | python -m json.tool
# Expected: 200 OK, description = null

# B4.5 — Update non-existent project
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Ghost"}' \
  "$BASE_URL/projects/00000000-0000-0000-0000-000000000000" | python -m json.tool
# Expected: 404 Not Found

# B4.6 — Invalid status
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "invalid"}' \
  "$BASE_URL/projects/$PROJECT_ID" | python -m json.tool
# Expected: 422 Validation Error

# B4.7 — Empty body
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' \
  "$BASE_URL/projects/$PROJECT_ID" | python -m json.tool
# Expected: 200 OK, no changes made (returns current state)

# B4.8 — No auth
curl -s -X PATCH -H "Content-Type: application/json" \
  -d '{"name": "Unauthorized"}' \
  "$BASE_URL/projects/$PROJECT_ID"
# Expected: 401 Unauthorized
```

### B5. Delete Project — DELETE /projects/{id}

```bash
# Create a project to delete first
DELETE_ID=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Project To Delete"}' \
  "$BASE_URL/projects" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# B5.1 — Soft delete
curl -s -o /dev/null -w "%{http_code}" -X DELETE -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects/$DELETE_ID"
# Expected: 204 No Content

# B5.2 — Verify deleted project not in list
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?search=Project%20To%20Delete" | python -m json.tool
# Expected: items = [], total = 0 (soft-deleted, not visible)

# B5.3 — Verify deleted project not accessible by ID
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects/$DELETE_ID" | python -m json.tool
# Expected: 404 Not Found (soft-deleted)

# B5.4 — Double delete (delete already deleted)
curl -s -o /dev/null -w "%{http_code}" -X DELETE -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects/$DELETE_ID"
# Expected: 404 Not Found

# B5.5 — Delete non-existent project
curl -s -o /dev/null -w "%{http_code}" -X DELETE -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects/00000000-0000-0000-0000-000000000000"
# Expected: 404 Not Found

# B5.6 — No auth
curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$BASE_URL/projects/$DELETE_ID"
# Expected: 401 Unauthorized
```

### B6. Data Integrity Checks

```bash
# B6.1 — created_by is always from JWT
# Create a project, then verify created_by matches the authenticated user
NEW_ID=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Creator Test"}' \
  "$BASE_URL/projects" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects/$NEW_ID" | python -c "import sys,json; d=json.load(sys.stdin); print(f'created_by: {d[\"created_by\"]}')"
# Expected: Your user UUID (not null, not any client-supplied value)

# B6.2 — Timestamps auto-set
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects/$NEW_ID" | python -c "import sys,json; d=json.load(sys.stdin); print(f'created_at: {d[\"created_at\"]}'); print(f'updated_at: {d[\"updated_at\"]}')"
# Expected: Both timestamps are set and in ISO format

# B6.3 — deleted_at is null for active projects
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects/$NEW_ID" | python -c "import sys,json; d=json.load(sys.stdin); print(f'deleted_at: {d[\"deleted_at\"]}')"
# Expected: deleted_at: None

# B6.4 — Pagination total is correct
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE_URL/projects?page_size=1" | python -c "import sys,json; d=json.load(sys.stdin); print(f'total: {d[\"total\"]}, items_returned: {len(d[\"items\"])}')"
# Expected: total = total number of non-deleted projects, items_returned = 1
```

### B7. Via FastAPI Docs (Interactive)

1. Open `http://localhost:8000/docs` in browser
2. Click **Authorize** button at the top
3. Paste your Bearer token in the "Value" field (just the token, no "Bearer" prefix)
4. Click "Authorize"
5. Now you can test each endpoint interactively:
   - **GET /api/v1/projects** — Try different query params (search, status, sort_by, sort_dir, page, page_size)
   - **GET /api/v1/projects/{project_id}** — Paste a valid UUID
   - **POST /api/v1/projects** — Use "Try it out" to send JSON body
   - **PATCH /api/v1/projects/{project_id}** — Partial updates
   - **DELETE /api/v1/projects/{project_id}** — Soft delete

---

## Cleanup After Testing

After running all tests, you may want to clean up test-created projects:
1. Go to `/projects` in the UI
2. Click each test project you created
3. Delete via the Delete button
4. Or use curl DELETE calls for each test project ID
