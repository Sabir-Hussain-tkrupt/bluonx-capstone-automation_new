# Task 4.6: Vendor Selection UI - Manual Testing Guide

This guide covers end-to-end manual testing of the Vendor Selection UI implemented in Task 4.6. It walks through every screen, interaction, and edge case across the four main areas:

1. **Task Detail Page** - Bid Packages section
2. **Bid Package Creation Wizard** (3 steps: Configure, Select Vendors, Review & Send)
3. **Bid Package Detail Page** (invitations, email log, countdown)
4. **React Query hooks & API integration**

---

## Prerequisites & Test Data Setup

### Required Database Records

Before testing, ensure the following data exists in your Supabase database:

#### 1. Users
- At least one user with role `project_manager` (the logged-in user for testing)
- Optionally one `admin` user

#### 2. Trades
```sql
-- Ensure at least 2 trades exist
INSERT INTO trades (id, name) VALUES
  ('trade-electrical', 'Electrical'),
  ('trade-plumbing', 'Plumbing');
```

#### 3. Projects
```sql
-- A project with valid coordinates (needed for distance filtering)
INSERT INTO projects (id, name, status, latitude, longitude) VALUES
  ('proj-1', 'Test Development Project', 'active', 29.7604, -95.3698); -- Houston, TX
```

#### 4. Project Documents (for Step 1 document attachment)
```sql
INSERT INTO project_documents (id, project_id, file_name, file_path, file_type, file_size, uploaded_by) VALUES
  ('doc-1', 'proj-1', 'Site Plans v3.pdf', 'proj-1/site-plans-v3.pdf', 'application/pdf', 2048000, '<your-user-id>'),
  ('doc-2', 'proj-1', 'Geotech Report.pdf', 'proj-1/geotech-report.pdf', 'application/pdf', 5120000, '<your-user-id>'),
  ('doc-3', 'proj-1', 'Scope of Work.docx', 'proj-1/scope-of-work.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 102400, '<your-user-id>');
```

#### 5. Tasks
```sql
-- A competitive task (main test case)
INSERT INTO tasks (id, project_id, name, trade_id, bid_type, status, phase, budget_estimate, sort_order) VALUES
  ('task-comp-1', 'proj-1', 'Electrical Rough-In', 'trade-electrical', 'competitive', 'draft', 'development', 250000, 1);

-- An internal task (should NOT show bid packages section)
INSERT INTO tasks (id, project_id, name, trade_id, bid_type, status, phase, sort_order) VALUES
  ('task-internal-1', 'proj-1', 'Budget Reserve', 'trade-electrical', 'internal', 'draft', 'development', 2);

-- A direct_assign task (should NOT show bid packages section)
INSERT INTO tasks (id, project_id, name, trade_id, bid_type, status, phase, sort_order) VALUES
  ('task-direct-1', 'proj-1', 'Emergency Plumbing', 'trade-plumbing', 'direct_assign', 'draft', 'development', 3);
```

#### 6. Vendors (mix of qualified and disqualified)
```sql
-- Qualified vendor: nearby, insured, has capacity
INSERT INTO vendors (id, company_name, onboarding_status, latitude, longitude, insurance_expiration_date, bonding_capacity, max_active_jobs) VALUES
  ('v-1', 'ABC Electrical LLC', 'approved', 29.77, -95.38, '2027-01-01', 500000, 5),
  ('v-2', 'Delta Power Systems', 'approved', 29.75, -95.36, '2026-12-15', 300000, 3),
  ('v-3', 'Spark Electric Co', 'approved', 29.80, -95.40, '2026-08-01', 200000, 4);

-- Disqualified vendor: expired insurance
INSERT INTO vendors (id, company_name, onboarding_status, latitude, longitude, insurance_expiration_date, bonding_capacity, max_active_jobs) VALUES
  ('v-disq-1', 'Old Wire Services', 'approved', 29.76, -95.37, '2024-01-01', 100000, 2);

-- Disqualified vendor: too far away (200+ miles)
INSERT INTO vendors (id, company_name, onboarding_status, latitude, longitude, insurance_expiration_date) VALUES
  ('v-disq-2', 'Faraway Electric', 'approved', 32.78, -96.80, '2027-06-01'); -- Dallas, TX

-- Vendor with unresolved flags
INSERT INTO vendor_flags (vendor_id, flag_type, status) VALUES
  ('v-3', 'performance_issue', 'open');
```

#### 7. Vendor Contacts
```sql
INSERT INTO vendor_contacts (id, vendor_id, full_name, email, phone, is_primary) VALUES
  ('vc-1', 'v-1', 'John Smith', 'john@abcelectric.com', '555-0101', true),
  ('vc-2', 'v-2', 'Jane Doe', 'jane@deltapower.com', '555-0202', true),
  ('vc-3', 'v-3', 'Bob Wilson', 'bob@sparkelectric.com', '555-0303', true),
  ('vc-4', 'v-disq-1', 'Old Timer', 'old@oldwire.com', '555-0404', true),
  ('vc-5', 'v-disq-2', 'Far Guy', 'far@faraway.com', '555-0505', true);
```

#### 8. Vendor-Trade Assignments
```sql
INSERT INTO vendor_trades (vendor_id, trade_id) VALUES
  ('v-1', 'trade-electrical'),
  ('v-2', 'trade-electrical'),
  ('v-3', 'trade-electrical'),
  ('v-disq-1', 'trade-electrical'),
  ('v-disq-2', 'trade-electrical');
```

#### 9. Bid Templates (for Step 1 template selection)
```sql
-- Template matching the task's trade (should appear in "Recommended")
INSERT INTO bid_templates (id, name, trade_id, is_lump_sum) VALUES
  ('bt-1', 'Electrical Standard Template', 'trade-electrical', false);
INSERT INTO bid_template_items (id, bid_template_id, label, sort_order) VALUES
  ('bti-1', 'bt-1', 'Rough-in labor', 1),
  ('bti-2', 'bt-1', 'Materials', 2),
  ('bti-3', 'bt-1', 'Panel installation', 3);

-- General template (no trade, should appear in "General Templates")
INSERT INTO bid_templates (id, name, trade_id, is_lump_sum) VALUES
  ('bt-2', 'General Lump Sum', NULL, true);
INSERT INTO bid_template_items (id, bid_template_id, label, sort_order) VALUES
  ('bti-4', 'bt-2', 'Total bid amount', 1);

-- Template for a different trade (should appear in "Other Templates")
INSERT INTO bid_templates (id, name, trade_id, is_lump_sum) VALUES
  ('bt-3', 'Plumbing Template', 'trade-plumbing', false);
INSERT INTO bid_template_items (id, bid_template_id, label, sort_order) VALUES
  ('bti-5', 'bt-3', 'Pipe labor', 1),
  ('bti-6', 'bt-3', 'Fixtures', 2);
```

### Backend Services Running
- FastAPI backend on `http://localhost:8000`
- Supabase local/cloud with valid `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`
- Email service configured (or mock email provider enabled for local testing)

### Frontend Running
```bash
cd frontend && npm run dev
```

---

## Section 1: Task Detail Page - Bid Packages Section

**Route:** `/projects/:id/tasks/:taskId`

### TC-1.1: Competitive task shows "Start Bidding" button
| Step | Action | Expected |
|------|--------|----------|
| 1 | Navigate to the competitive task detail page (`task-comp-1`) | Page loads with task info |
| 2 | Scroll to "Bid Packages" section | Section is visible below task details |
| 3 | Observe the button | "Start Bidding" button appears (since no bid packages exist yet) |
| 4 | Observe the table | BidPackagesTable shows empty state: "No bid packages yet" |

### TC-1.2: Internal task hides bid packages section
| Step | Action | Expected |
|------|--------|----------|
| 1 | Navigate to the internal task detail page (`task-internal-1`) | Page loads |
| 2 | Look for "Bid Packages" section | Section is **not rendered** at all. No "Start Bidding" button |

### TC-1.3: Direct-assign task hides bid packages section
| Step | Action | Expected |
|------|--------|----------|
| 1 | Navigate to the direct-assign task detail page (`task-direct-1`) | Page loads |
| 2 | Look for "Bid Packages" section | Section is **not rendered** at all |

### TC-1.4: "Start Bidding" navigates to wizard
| Step | Action | Expected |
|------|--------|----------|
| 1 | On competitive task detail, click "Start Bidding" | Navigates to `/projects/proj-1/tasks/task-comp-1/create-bid-package` |
| 2 | Observe the wizard | 3-step wizard loads with step 1 (Configure) active |

### TC-1.5: After bid package exists, button shows "Start New Round"
| Step | Action | Expected |
|------|--------|----------|
| 1 | After successfully creating a bid package, return to task detail | Button text changes to "Start New Round" |
| 2 | BidPackagesTable shows the created bid package | Row with Round #, Deadline, Status (open), Submitted/Total counts |

### TC-1.6: Bid package table row click navigates to detail
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click a row in the BidPackagesTable | Navigates to `/projects/:id/tasks/:taskId/bid-packages/:bidPackageId` |

### TC-1.7: Button hidden when task status is not "draft"
| Step | Action | Expected |
|------|--------|----------|
| 1 | Change task status to `awarded` in DB, then navigate to task detail | Bid Packages section visible but "Start Bidding"/"Start New Round" button is hidden |

---

## Section 2: Bid Package Creation Wizard

**Route:** `/projects/:id/tasks/:taskId/create-bid-package`

### Step Indicator Bar

### TC-2.0: Step indicator displays correctly
| Step | Action | Expected |
|------|--------|----------|
| 1 | Load wizard (Step 1) | Step 1 circle has border highlight (active), Steps 2 and 3 are grayed out |
| 2 | Advance to Step 2 | Step 1 circle filled (completed with checkmark), Step 2 highlighted, Step 3 grayed |
| 3 | Advance to Step 3 | Steps 1+2 filled (checkmarks), Step 3 highlighted |
| 4 | On desktop (>640px) | Step labels ("Configure", "Select Vendors", "Review & Send") are visible |
| 5 | On mobile (<640px) | Step labels hidden, only numbered circles visible |

---

### Step 1: Configure

### TC-2.1: Deadline defaults to 14 days from now
| Step | Action | Expected |
|------|--------|----------|
| 1 | Load wizard Step 1 | Deadline input pre-filled with date 14 days from today at 5:00 PM |
| 2 | Observe format | Uses `datetime-local` HTML input (browser-native date/time picker) |

### TC-2.2: Deadline validation - empty
| Step | Action | Expected |
|------|--------|----------|
| 1 | Clear the deadline field | Field is empty |
| 2 | Click "Next: Select Vendors" | Error message appears: "Deadline is required." |
| 3 | Do not advance | Stays on Step 1 |

### TC-2.3: Deadline validation - past date
| Step | Action | Expected |
|------|--------|----------|
| 1 | Set deadline to yesterday | Field shows a past date/time |
| 2 | Click "Next: Select Vendors" | Error message: "Deadline must be in the future." |
| 3 | Fix deadline to a future date | Error clears as you type |

### TC-2.4: Template selection - grouped correctly
| Step | Action | Expected |
|------|--------|----------|
| 1 | Observe template section while it loads | 3 skeleton placeholders shown |
| 2 | After loading, check groups | **Recommended** section shows "Electrical Standard Template" (with gold star icon, subtitle "Matches this task's trade") |
| 3 | Check General group | "General Lump Sum" in "General Templates" section |
| 4 | Check Other group | "Plumbing Template" in "Other Templates" section |

### TC-2.5: Template selection - card interaction
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Electrical Standard Template" card | Card border turns primary color, background tints blue. Shows "Structured" badge and "3 items" |
| 2 | Click "General Lump Sum" card | Previous card deselects, new card highlights. Shows "Lump Sum" badge and "1 items" |
| 3 | Only one template selected at a time | Radio-style behavior (not multi-select) |

### TC-2.6: Template validation - none selected
| Step | Action | Expected |
|------|--------|----------|
| 1 | Don't select any template | No card highlighted |
| 2 | Click "Next: Select Vendors" | Red alert: "Please select a bid template." |

### TC-2.7: No templates available
| Step | Action | Expected |
|------|--------|----------|
| 1 | Delete all bid templates from DB, then load wizard | Warning alert: "No templates available. Create a bid template first before creating a bid package." |

### TC-2.8: Project documents - all pre-checked
| Step | Action | Expected |
|------|--------|----------|
| 1 | Observe document checkboxes after loading | All 3 documents checked by default |
| 2 | Each shows file name, type, and size | "Site Plans v3.pdf", "application/pdf", "2.0 MB" |

### TC-2.9: Project documents - toggle individual
| Step | Action | Expected |
|------|--------|----------|
| 1 | Uncheck "Geotech Report.pdf" | Only 2 documents remain checked |
| 2 | Re-check it | Back to 3 checked |

### TC-2.10: Project documents - Select/Deselect All
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Deselect All" link | All checkboxes unchecked. Link text changes to "Select All" |
| 2 | Click "Select All" | All checkboxes re-checked. Link text changes to "Deselect All" |

### TC-2.11: No project documents
| Step | Action | Expected |
|------|--------|----------|
| 1 | Remove all project_documents from DB, reload wizard | Text: "No project documents uploaded yet." No checkboxes, no select/deselect link |

### TC-2.12: Step 1 data persists on back navigation
| Step | Action | Expected |
|------|--------|----------|
| 1 | Set deadline, select template, uncheck 1 document | Data entered |
| 2 | Click "Next", arrive at Step 2 | Step 2 loads |
| 3 | Click "Back" | Return to Step 1 with all previous selections intact (same deadline, same template highlighted, same document checkboxes) |

---

### Step 2: Select Vendors

### TC-2.20: Qualified vendors load with skeleton
| Step | Action | Expected |
|------|--------|----------|
| 1 | Advance to Step 2 | Skeleton loading state briefly shown (2 skeleton bars) |
| 2 | After load | Qualified vendors table appears with all vendors pre-checked |

### TC-2.21: All qualified vendors pre-checked
| Step | Action | Expected |
|------|--------|----------|
| 1 | Observe checkboxes | All qualified vendor rows have checked checkboxes |
| 2 | Header shows count | "Qualified Vendors (3)" title, "3 of 5 selected" subtitle |

### TC-2.22: Vendor table columns
| Step | Action | Expected |
|------|--------|----------|
| 1 | On desktop (>1024px) | All columns visible: Checkbox, Company, Contact, Email, Distance, Insurance, Capacity, Flags |
| 2 | On tablet (768-1024px) | Email and Capacity columns hidden (responsive `hidden lg:table-cell`) |
| 3 | On mobile (<768px) | Only Checkbox, Company, Distance, Flags visible. Contact shown below company name in smaller text |

### TC-2.23: Sort by distance (default)
| Step | Action | Expected |
|------|--------|----------|
| 1 | Default sort | Vendors sorted by distance ascending (nearest first) |
| 2 | Verify distances | Each row shows distance in miles (e.g., "1.2 mi") |

### TC-2.24: Sort by company name
| Step | Action | Expected |
|------|--------|----------|
| 1 | Change sort dropdown to "Company Name" | Table re-sorts alphabetically by company name |

### TC-2.25: Sort by capacity
| Step | Action | Expected |
|------|--------|----------|
| 1 | Change sort dropdown to "Capacity" | Table re-sorts by available capacity descending (most capacity first) |
| 2 | Capacity column shows | `current_active_jobs/max_active_jobs` format (e.g., "1/5") |

### TC-2.26: Toggle individual vendor
| Step | Action | Expected |
|------|--------|----------|
| 1 | Uncheck "Delta Power Systems" | Row no longer has blue tint. Selection count decreases |
| 2 | Re-check it | Row gets blue tint back. Count increases |

### TC-2.27: Select All / Deselect All
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Deselect All" | All qualified vendor checkboxes unchecked. Link text changes to "Select All" |
| 2 | Click "Select All" | All qualified vendors re-checked |

### TC-2.28: Vendor row expansion (click row)
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click anywhere on a vendor row (not the checkbox) | Row expands below showing "Contact Details" section |
| 2 | Details shown | Name, Email, Phone in a 3-column grid on desktop |
| 3 | Click the row again | Expansion collapses |
| 4 | Click a different row | Previous row collapses, new one expands (only one expanded at a time) |

### TC-2.29: Vendor with flags
| Step | Action | Expected |
|------|--------|----------|
| 1 | Find "Spark Electric Co" (has unresolved flag) | Warning triangle icon + "1" in Flags column |
| 2 | Hover over the flag icon | Tooltip shows flag reason (e.g., "performance issue") |
| 3 | Expand the row | Flag section appears below contacts showing flag reasons as warning badges |

### TC-2.30: Insurance warning styling
| Step | Action | Expected |
|------|--------|----------|
| 1 | If a vendor has `insurance_days_remaining < 30` | Insurance date shows in warning/orange text instead of default gray |

### TC-2.31: Vendor with no contact
| Step | Action | Expected |
|------|--------|----------|
| 1 | If a vendor has no primary_contact (null) | Checkbox is disabled. Contact column shows em-dash. Cannot be selected |
| 2 | Expand the row | Shows "No contacts available for this vendor." |

### TC-2.32: Disqualified vendors section - collapsed by default
| Step | Action | Expected |
|------|--------|----------|
| 1 | Observe below qualified vendors table | Card with "Show 2 disqualified vendors" header |
| 2 | Disqualified vendor data is **not** visible | Section is collapsed |

### TC-2.33: Expand disqualified vendors
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Show 2 disqualified vendors" | Chevron rotates, table expands showing disqualified vendors |
| 2 | Columns | Checkbox, Company, Contact, Reasons |
| 3 | Reasons column | Red badges showing disqualification reasons (e.g., "expired insurance", "outside radius") |

### TC-2.34: Override disqualified vendor - confirmation modal
| Step | Action | Expected |
|------|--------|----------|
| 1 | Check the checkbox for "Old Wire Services" | Modal opens: "Include Disqualified Vendor?" |
| 2 | Modal content | Shows vendor name in bold, lists disqualification reasons in a bulleted list |
| 3 | Click "Cancel" | Modal closes, vendor stays unchecked |
| 4 | Check again, click "Include Anyway" | Modal closes, vendor is now checked and included in selection count |

### TC-2.35: Uncheck overridden disqualified vendor
| Step | Action | Expected |
|------|--------|----------|
| 1 | After overriding, uncheck the disqualified vendor | Vendor is unchecked immediately (no modal needed for unchecking) |

### TC-2.36: Validation - no vendors selected
| Step | Action | Expected |
|------|--------|----------|
| 1 | Deselect all vendors (both qualified and any overridden disqualified) | All unchecked |
| 2 | Click "Next: Review & Send" | Red alert: "Select at least one vendor to continue." |

### TC-2.37: Filtering warnings display
| Step | Action | Expected |
|------|--------|----------|
| 1 | If the API returns `warnings` array (e.g., "Project has no coordinates") | Yellow warning alert at top of Step 2 with bulleted list of warnings |

### TC-2.38: Step 2 selections persist on back navigation
| Step | Action | Expected |
|------|--------|----------|
| 1 | Uncheck 1 qualified vendor, override-include 1 disqualified vendor | Custom selection state |
| 2 | Click "Next" (to Step 3) | Step 3 loads |
| 3 | Click "Back" | Return to Step 2 with selections preserved (same vendors checked/unchecked as before) |

### TC-2.39: API error state
| Step | Action | Expected |
|------|--------|----------|
| 1 | Simulate API failure (stop backend, or bad task ID) | Red alert: "Failed to load vendors. Could not fetch qualified vendors. Please try again." |

---

### Step 3: Review & Send

### TC-2.40: Summary cards correct
| Step | Action | Expected |
|------|--------|----------|
| 1 | Arrive at Step 3 | 4 summary cards displayed in a grid |
| 2 | "Deadline" card | Shows formatted deadline (e.g., "Thu, Apr 24, 2026, 05:00 PM") |
| 3 | "Template" card | Shows selected template name (e.g., "Electrical Standard Template") |
| 4 | "Documents" card | Shows count (e.g., "3") |
| 5 | "Vendors" card | Shows count of selected vendors (e.g., "3") |

### TC-2.41: Selected vendors table (read-only)
| Step | Action | Expected |
|------|--------|----------|
| 1 | Observe "Selected Vendors" table | Columns: Company, Contact, Email. No checkboxes, no actions |
| 2 | Each row | Shows company name, primary contact name, primary contact email |
| 3 | Table is non-interactive | No row expansion, no hover actions |

### TC-2.42: "Back" button returns to Step 2
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Back" on Step 3 | Returns to Step 2 with all vendor selections preserved |

### TC-2.43: "Send Invitations" opens confirmation modal
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Send Invitations" | Modal opens: "Send Bid Invitations" |
| 2 | Modal text | "Send bid invitations to **3 vendors** for **Electrical Rough-In**?" |
| 3 | Subtext | "This will email each vendor a unique bid portal link. This action cannot be undone." |
| 4 | Buttons | "Cancel" (ghost) and "Send 3 Invitations" (primary) |

### TC-2.44: Cancel in confirmation modal
| Step | Action | Expected |
|------|--------|----------|
| 1 | Open confirmation modal, click "Cancel" | Modal closes. Stays on Step 3. Nothing sent |

### TC-2.45: Successful submission
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Send N Invitations" in modal | Button shows loading spinner. "Cancel" button disabled. Modal cannot be closed |
| 2 | After success | Success toast: "3 invitations sent successfully." |
| 3 | Navigation | Redirected to bid package detail page (`/projects/:id/tasks/:taskId/bid-packages/:newId`) |

### TC-2.46: Partial failure submission
| Step | Action | Expected |
|------|--------|----------|
| 1 | Simulate partial failure (e.g., one vendor has invalid email in DB) | Warning toast: "2 invitations sent. 1 failed -- check the detail page for specifics." |
| 2 | Navigation | Still navigates to detail page (partial success is acceptable) |

### TC-2.47: Full failure submission
| Step | Action | Expected |
|------|--------|----------|
| 1 | Simulate complete API failure (stop backend) | Danger toast: "Failed to create bid package." |
| 2 | Stays on Step 3 | Does not navigate. User can retry |

### TC-2.48: Submission button disabled while loading
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Send Invitations" and observe | Both "Back" button on Step 3 and "Cancel"/"Send" in modal are disabled during API call |

---

## Section 3: Bid Package Detail Page

**Route:** `/projects/:id/tasks/:taskId/bid-packages/:bidPackageId`

### TC-3.1: Page loads with correct data
| Step | Action | Expected |
|------|--------|----------|
| 1 | Navigate to bid package detail (or get redirected after creation) | Page loads showing header, summary cards, invitations table |
| 2 | Header | "Round 1 -- Electrical Rough-In" |
| 3 | Status badge | Shows "open" with appropriate info-blue styling |

### TC-3.2: Loading skeleton
| Step | Action | Expected |
|------|--------|----------|
| 1 | Observe page during data fetch | Skeleton layout: wide bar (60% for title), 4 equal cards, tall content block |

### TC-3.3: Error state - bid package not found
| Step | Action | Expected |
|------|--------|----------|
| 1 | Navigate with invalid bidPackageId | Red danger alert: "Bid package not found. The bid package you are looking for does not exist." |

### TC-3.4: Countdown timer - future deadline
| Step | Action | Expected |
|------|--------|----------|
| 1 | With deadline set 14 days from now | Text shows e.g., "14d 3h remaining" in default gray color |
| 2 | Wait 1 minute | Timer updates automatically (setInterval every 60s) |
| 3 | When less than 1 day remaining | Shows hours and minutes (e.g., "5h 32m remaining") |

### TC-3.5: Countdown timer - deadline passed
| Step | Action | Expected |
|------|--------|----------|
| 1 | Set deadline to a past date in DB, reload | Shows "Deadline passed" in red/danger text |
| 2 | "Close Bidding" button | Appears in the header actions area (only visible when deadline passed AND status is "open") |

### TC-3.6: Summary cards
| Step | Action | Expected |
|------|--------|----------|
| 1 | "Total Invited" card | Shows total count from `invitation_summary.total` in dark text |
| 2 | "Submitted" card | Shows submitted count in green |
| 3 | "Pending" card | Shows `sent + opened` count in blue |
| 4 | "Declined / Expired" card | Shows `declined + expired + no_response` count in gray |

### TC-3.7: Back button navigation
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click the left-arrow back button | Navigates to `/projects/:id/tasks/:taskId` (task detail page) |

---

### Invitations Table

### TC-3.10: Table columns
| Step | Action | Expected |
|------|--------|----------|
| 1 | Observe invitations table | Columns: Vendor, Contact, Email, Status, Sent, Opened, Responded, Actions |
| 2 | Status column | StatusBadge with appropriate color for each status |
| 3 | Date columns | Formatted as "Apr 10, 05:30 PM" or em-dash if null |

### TC-3.11: Resend invitation
| Step | Action | Expected |
|------|--------|----------|
| 1 | Find an invitation with status "sent" or "opened" or "no_response" | "Resend" button visible in Actions column |
| 2 | Click "Resend" | Button shows loading spinner. All other action buttons disabled |
| 3 | Success | Toast: "Invitation resent." Button returns to normal |
| 4 | Error | Toast with error message. Button returns to normal |

### TC-3.12: Mark as Declined
| Step | Action | Expected |
|------|--------|----------|
| 1 | Find invitation with status "sent" or "opened" | "Mark Declined" button visible |
| 2 | Click "Mark Declined" | Loading state. On success: toast "Invitation marked as declined." |
| 3 | After success | StatusBadge changes to "declined" (red). Action buttons disappear for this row |

### TC-3.13: Mark as No Response
| Step | Action | Expected |
|------|--------|----------|
| 1 | Find invitation with status "sent" or "opened" | "No Response" button visible |
| 2 | Click "No Response" | On success: toast "Invitation marked as no response." |
| 3 | After success | StatusBadge changes to "no_response" (neutral). Action buttons disappear for this row |

### TC-3.14: Action buttons hidden for terminal statuses
| Step | Action | Expected |
|------|--------|----------|
| 1 | Invitation with status "submitted" | No action buttons visible (submitted is terminal) |
| 2 | Invitation with status "declined" | No action buttons visible |
| 3 | Invitation with status "expired" | No action buttons visible |

### TC-3.15: Concurrent action prevention
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Resend" on one invitation | All other action buttons (Resend, Mark Declined, No Response) across ALL rows become disabled |
| 2 | After action completes | All buttons re-enable |

---

### Documents Section

### TC-3.20: Documents displayed
| Step | Action | Expected |
|------|--------|----------|
| 1 | If bid package has documents | Card with "Attached Documents" header, list of file names with document icon |
| 2 | Each document | Shows file name (or "Unnamed document" if null) |

### TC-3.21: No documents
| Step | Action | Expected |
|------|--------|----------|
| 1 | If `documents` array is empty | Entire documents card is hidden (not rendered) |

---

### Email Log Section

### TC-3.30: Collapsed by default
| Step | Action | Expected |
|------|--------|----------|
| 1 | Observe "Email Log" card | Header visible with chevron pointing down. No table content visible |
| 2 | Network tab | **No API call** for email log on page load (lazy loading) |

### TC-3.31: Expand email log
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Email Log" header | Chevron rotates 180 degrees. Table appears below |
| 2 | Network tab | API call fires: `GET /api/v1/bid-packages/:id/email-log` |
| 3 | During fetch | Loading state in table area |
| 4 | After load | Table with columns: Recipient, Type, Subject, Status, Sent At, Error |

### TC-3.32: Email log table data
| Step | Action | Expected |
|------|--------|----------|
| 1 | Type column | Shows email type with underscores replaced by spaces, capitalized (e.g., "bid invitation") |
| 2 | Status column | StatusBadge (e.g., "sent", "delivered", "bounced") |
| 3 | Error column | If error exists, shows in red text. Otherwise em-dash |
| 4 | Sent At column | Formatted date/time in gray |

### TC-3.33: Empty email log
| Step | Action | Expected |
|------|--------|----------|
| 1 | If no emails logged | Table shows "No emails logged yet." empty state |

### TC-3.34: Collapse email log
| Step | Action | Expected |
|------|--------|----------|
| 1 | Click "Email Log" header again | Chevron rotates back. Table hides |

---

### Action Buttons (Header)

### TC-3.40: Cancel Bid Package button
| Step | Action | Expected |
|------|--------|----------|
| 1 | When status is "open" | Red "Cancel Bid Package" button visible in header |
| 2 | Click it | Confirmation modal: "Cancel Bid Package" |
| 3 | Modal text | "Are you sure you want to cancel this bid package? All pending invitations will be marked as expired. This action cannot be undone." |
| 4 | Click "Keep Open" | Modal closes, no action taken |
| 5 | Click "Cancel Bid Package" | Modal closes, info toast: "Cancel bid package is not yet implemented." (placeholder -- API not yet built) |

### TC-3.41: Close Bidding button
| Step | Action | Expected |
|------|--------|----------|
| 1 | When deadline is passed AND status is "open" | "Close Bidding" outline button visible |
| 2 | When deadline is NOT passed | Button is not visible |
| 3 | When status is NOT "open" | Button is not visible |

### TC-3.42: No action buttons when closed/cancelled
| Step | Action | Expected |
|------|--------|----------|
| 1 | When bid package status is "closed" or "cancelled" | Neither "Cancel Bid Package" nor "Close Bidding" buttons are visible |

---

## Section 4: React Query & API Integration

### TC-4.1: Query key cache invalidation after creation
| Step | Action | Expected |
|------|--------|----------|
| 1 | Create a bid package via wizard | Redirected to detail page |
| 2 | Navigate back to task detail | BidPackagesTable automatically shows the new package (cache invalidated by `useCreateBidPackage`) |
| 3 | No manual refresh needed | React Query cache for `bidPackages.forTask` was invalidated |

### TC-4.2: Cache invalidation after resend
| Step | Action | Expected |
|------|--------|----------|
| 1 | Resend an invitation on detail page | After success, bid package detail refreshes (cache for `bidPackages.detail` invalidated) |

### TC-4.3: Cache invalidation after status update
| Step | Action | Expected |
|------|--------|----------|
| 1 | Mark invitation as declined | After success, bid package detail refreshes. Summary cards update. Status badge in table changes |

### TC-4.4: Stale-while-revalidate behavior
| Step | Action | Expected |
|------|--------|----------|
| 1 | Navigate away and back to bid package detail | Data shows immediately from cache, background refetch may update if data changed |

---

## Section 5: Edge Cases & Boundary Conditions

### TC-5.1: Very long company/template names
| Step | Action | Expected |
|------|--------|----------|
| 1 | Create a vendor with a 100-character company name | Name truncates with ellipsis in tables. Full name visible in expanded row |

### TC-5.2: Unicode characters in vendor names
| Step | Action | Expected |
|------|--------|----------|
| 1 | Vendor with name "Empresa Electrica S.A. de C.V." | Displays correctly, no rendering issues |

### TC-5.3: Single vendor selected
| Step | Action | Expected |
|------|--------|----------|
| 1 | Select only 1 vendor in Step 2, proceed to Step 3 | Summary shows "1" vendor. Confirmation modal says "Send 1 Invitation" (singular) |

### TC-5.4: All documents deselected
| Step | Action | Expected |
|------|--------|----------|
| 1 | Deselect all documents in Step 1 | Allowed (documents are optional). Step 3 shows "0" in documents card |

### TC-5.5: Only disqualified vendors available
| Step | Action | Expected |
|------|--------|----------|
| 1 | Task where all vendors are disqualified | Qualified vendors table shows "No qualified vendors found for this task." |
| 2 | PM must override-include at least 1 disqualified vendor to proceed | Validation prevents advancing with 0 selected |

### TC-5.6: Wizard with no qualified vendors at all
| Step | Action | Expected |
|------|--------|----------|
| 1 | Task with a trade that no vendor has | Empty qualified table, no disqualified section |
| 2 | Cannot proceed past Step 2 | Validation error: "Select at least one vendor to continue." |

### TC-5.7: Rapid double-click on "Send Invitations"
| Step | Action | Expected |
|------|--------|----------|
| 1 | Quickly double-click "Send Invitations" in modal | Only one API call fires (button is disabled after first click via `isSubmitting`) |

### TC-5.8: Browser back button during wizard
| Step | Action | Expected |
|------|--------|----------|
| 1 | On Step 2 of wizard, press browser back | Navigates away from wizard entirely (back to task detail). Wizard state is lost |
| 2 | This is expected behavior | Wizard uses internal step state, not URL-based routing |

### TC-5.9: Direct URL access to wizard with invalid task
| Step | Action | Expected |
|------|--------|----------|
| 1 | Navigate to `/projects/fake/tasks/fake/create-bid-package` | BidPackageCreatePage shows loading, then error alert when task fails to load |

### TC-5.10: Non-competitive task wizard access via URL
| Step | Action | Expected |
|------|--------|----------|
| 1 | Navigate to wizard URL for an internal/direct_assign task | Error alert: "Bid packages are only available for competitive tasks." |

---

## Section 6: Responsive Design Checks

### TC-6.1: Wizard on mobile (< 640px)
| Step | Action | Expected |
|------|--------|----------|
| 1 | Load wizard on mobile viewport | Step labels hidden (only circles). Cards stack vertically. Full-width buttons |

### TC-6.2: Vendor table on mobile
| Step | Action | Expected |
|------|--------|----------|
| 1 | Step 2 on mobile | Contact name appears below company name in same cell. Email, Insurance, Capacity columns hidden. Distance and Flags remain visible |

### TC-6.3: Detail page on mobile
| Step | Action | Expected |
|------|--------|----------|
| 1 | Bid package detail on mobile | Summary cards: 2-column grid. Header stacks vertically. Tables use `mobileTitle` prop for card-style rendering |

### TC-6.4: Invitations table on mobile
| Step | Action | Expected |
|------|--------|----------|
| 1 | InvitationsTable on mobile | Uses shared `<Table>` mobileTitle="vendor_company_name". Each invitation renders as a card with vendor name as title |

---

## Section 7: Status Badge Verification

Verify the following statuses render with correct colors:

| Status | Expected Variant | Color |
|--------|-----------------|-------|
| `open` | info | Blue |
| `closed` | neutral | Gray |
| `sent` | info | Blue |
| `opened` | warning | Yellow/Amber |
| `submitted` | success | Green |
| `declined` | danger | Red |
| `expired` | neutral | Gray |
| `no_response` | neutral | Gray |
| `draft` | neutral | Gray |

---

## Section 8: Build Verification

### TC-8.1: TypeScript compilation
```bash
cd frontend && npm run build
```
- Expected: Zero new errors from `features/bids/**` files
- Pre-existing errors (AddressAutocomplete, TaskForm Zod overload) are unrelated

### TC-8.2: ESLint
```bash
cd frontend && npm run lint
```
- Expected: No new linting errors from Task 4.6 files

---

## Quick Smoke Test Checklist

For rapid verification, run through these steps in order:

- [ ] Navigate to competitive task detail -> see "Start Bidding" button
- [ ] Click "Start Bidding" -> wizard loads at Step 1
- [ ] Deadline pre-filled, select a template, docs all checked -> click Next
- [ ] Vendors load, all pre-checked, can sort -> click Next
- [ ] Review summary correct, click "Send Invitations" -> confirmation modal
- [ ] Confirm -> redirected to bid package detail with success toast
- [ ] Detail page: countdown timer, summary cards, invitations table all render
- [ ] Expand email log -> data loads lazily
- [ ] Go back to task detail -> bid package listed in table, button says "Start New Round"
- [ ] Navigate to internal task -> no bid packages section
- [ ] Navigate to direct_assign task -> no bid packages section
