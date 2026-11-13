# Phase 2 · Module 2 — Setup & Usage Runbook

How to switch on the project budget structure: the database migration, the backend and frontend deploy, and how to use the new screens.

**Order matters: database first, then backend, then frontend.** The new code reads the new database objects, while the old code ignores them, so applying the database first is always safe.

---

## 1. Database (Supabase SQL Editor)

Files: `database/migrations/20261118_financial_phase2/`. Phase 1 must already be applied.

1. Run `000_preflight_checks.sql`. Every row should be `OK` / `INFO`; row 1 shows `4.0.0 (20261111_financial_phase1)`.
2. Run `001_budget_structure.sql`. If Supabase warns about "destructive operations / RLS", choose **Run without RLS** (the file creates no tables). Expect "Success. No rows returned".
3. Run `002_verify_budget_structure.sql`. Expect 29 rows, all **PASS**, which leaves no data behind.
4. Optional, **test database only**: run `database/seed_data/dev_seed_financial_phase2.sql`. It needs `financial_settings.environment = "development"`, the same switch as the Phase 1 seed. It creates the project "Demo · Template Budget".
5. Check in **Storage** that a private bucket named `finance-documents` exists. The migration creates it; if it is missing, create it by hand as **private**, with no policies.

## 2. Backend

1. `backend/requirements.txt` gains **openpyxl**. Rebuild the image (`docker build` / your normal ECS pipeline) or run `pip install -r requirements.txt` locally.
2. Deploy as usual. No new environment variables are needed.
3. Check: `GET /health` is OK, and the API docs (`/docs`) list the new **Budgets**, **Budget Templates** and **Internal Invoices** sections.

Tests: `pytest` gives 1567 passed (98 of them new). The live-database tests are unchanged.

## 3. Frontend

Deploy as usual (Amplify). There are no new environment variables.

Tests: `npm test` gives 598 passed (20 new); `npm run lint` shows 0 errors; `npm run build` succeeds.

---

## 4. Using it

### Give people their roles (once)
**Settings → User Management →** row menu **→ Financial roles…** offers Field Manager, Executive and Finance (a person can hold several), plus "External / temporary field manager". The **Invite user** dialog has the same checkboxes for new people.

### Set up the standard template (admin, once)
**Settings → Budget Template.**
- Drag rows into the client's order, then add, edit or remove lines.
- Rows marked *(task slot)* are placeholders: tasks with the same **name** (or, failing that, the same **trade**) are placed there.
- Changing the template never changes budgets that already exist.

### Create a project budget (admin)
**Project → Budget tab → Create budget.**
- Optionally type a contingency %; empty means 15%.
- Every task becomes a line in template order, with its estimate as the starting amount.
- While the budget is a **Draft** you can:
  - edit amount, dates, payment terms, cash bucket and heading (row menu → **Edit**);
  - **Add line** (land, permit, impact fee, soft cost, long-tail, internal T&M) and **Remove line** (task lines go with their task);
  - use **Move up / Move down**;
  - use **Add T&M portion** on an activity (e.g. engineering bid + T&M);
  - set up **Phased closings** on a land line;
  - **Import** from Excel / CSV, which shows a preview before anything is written.
- **Baseline budget** freezes the original estimates and makes the total flat. From then on, money moves only through awards, variances and executive top-ups.

### What happens automatically
| You do (existing screens) | Budget reacts |
|---|---|
| Add a task | New budget line (draft: its estimate; baselined: $0) |
| Award a bid | Line = award amount; difference into / out of contingency |
| Vendor declines in DocuSign | Movement reversed |
| Contract signed in DocuSign | Line locked 🔒; dates filled from the contract |

If something ever looks out of step, use the Budget tab **⋯ → Sync awards**. It is safe to run any time.

### Internal invoices (field managers, PMs, finance, admins)
**Project → Invoices tab → + Upload Invoice** takes the payee, amount, number, date and file (PDF / image / Word / Excel, up to 25 MB).
- Row menu **→ Categorise & send for approval**: pick the internal T&M line. If the invoice is more than the line has left, the dialog shows the overage, which becomes a variance funded from contingency.
- Finance, executives and admins see every invoice; other users see the ones they uploaded.
- The approve / route / reject buttons for payments come in Phase 6. Until then, requests wait as *pending*.

### Export
**Budget tab → Export → Excel or CSV.** Available to every role. Amounts are exact to the cent.

---

## 5. Notes and limits

- **Spent** stays $0 until Phase 6 adds payment approval actions.
- Budget screens refresh after every change and when the browser tab regains focus. They are not realtime pushes; adding them would need the new tables in Supabase's realtime publication, which can be done later.
- A task added **after** baseline goes after the last line of the same type. Use Move up / down if it belongs elsewhere.
- Rollback (dev only): `099_rollback_budget_structure.sql` removes the Phase 2 procedures, views and trigger, and keeps the data.

---

## 6. Patch: budget envelope (Nov 13, 2026)

**Apply** in the Supabase SQL Editor, after Phase 2, from `database/migrations/20261119_financial_phase2_budget_envelope/`:
1. Run `001_budget_envelope.sql`. If Supabase warns about RLS, choose **Run without RLS**.
2. Run `002_verify_budget_envelope.sql`. Expect 14 rows, all PASS.

Then redeploy the backend and frontend (no new packages).

**What changes on screen**
- **Create budget** shows a preview. The total is the project's **Budget** value; contingency is the % of the base (e.g. $500,000 at 15% → $65,217.39 contingency).
- Tasks that are already **awarded** appear at the award amount and count as **Committed**. Lines whose contract is already signed appear locked 🔒.
- A new **Unallocated budget** line holds the part of the budget not yet on a line. While the budget is a draft, it grows or shrinks automatically when other lines change, so the total stays at the project budget.
- **Remaining** card = Total − Contingency − Committed. Per line, Remaining = Budget − Committed (the contingency line shows "—").
- If the lines add up to more than the project budget, a yellow warning says by how much.
- **⋯ → Reset draft budget** (admin, drafts only) starts a draft over.

**For budgets you already created as drafts before this patch** (e.g. Austin Development Site):
1. Budget tab → ⋯ → **Reset draft budget** → confirm.
2. Make sure the project has a **Budget** value (Edit project).
3. **Create budget** again: it now uses the project budget, contingency % and current awards.

Baselined budgets are not changed.
