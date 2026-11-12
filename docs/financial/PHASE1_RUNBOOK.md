# Phase 1 · Module 1 — Setup & Operating Runbook

How to apply the Financial Automation foundation (schema v4.0) to the BluOnX
databases, check it, and work with it until the Phase 2+ code arrives.

All files live in `database/migrations/20261111_financial_phase1/` unless noted.

---

## 0. Before you start (5 minutes)

- [ ] You can open the **dev** and **production** Supabase projects and use the **SQL Editor** in each.
- [ ] You know which tab is which. The project name is shown top-left in Supabase. Production gets its own browser window, so dev and prod never sit side by side.
- [ ] No backend or frontend deploy is needed. This phase is database only, and the running app keeps working unchanged.
- [ ] Have these files open: `000_preflight_checks.sql`, `001_financial_foundation.sql`, `002_verify_financial_foundation.sql`, and for dev `database/seed_data/dev_seed_financial_phase1.sql`.

> **How to run a file:** SQL Editor → **New query** → paste the **entire** file → **Run** (Ctrl+Enter).
> The editor shows the result of the last statement only. Every file here is written so that its last statement is the result you need to read.

---

## 1. Development database

### Step 1: Pre-flight (read-only)
Run `000_preflight_checks.sql`. You get a 13-row table.

| Row | Expect |
|---|---|
| 1–6, 10, 11, 13 | `OK` |
| 7 | `OK` "none — fresh install" (or `INFO` "all 19 present" if you already ran 001) |
| 8, 12 | `INFO`. Note the email types and row counts so you can compare them later. |
| any `STOP` | **Stop here** and send me the output. |

### Step 2: Apply the migration
Run `001_financial_foundation.sql`.
- Expected: **"Success. No rows returned."**
- If it fails, nothing is applied: the whole file is one transaction. Read the error:
  - `canceling statement due to lock timeout`: something was using a table. Wait a minute and run it again.
  - anything else: send me the message.

### Step 3: Verify
Run `002_verify_financial_foundation.sql`. You get 35 rows.
- All rows should say **PASS**.
- `SKIP` is acceptable only for **C08** (inserting into `auth.users` was not allowed) and **C33** (switching role was not allowed). Every other check still covers the rules.
- Any `FAIL` or `ABORTED` means you should not go to production. Send me the output.
- The script removes its own test data. Row **C99** confirms nothing was left behind.

### Step 4: Prove it is re-runnable
Run `001_financial_foundation.sql` **again** → it must succeed again. Then run `002` again → all PASS.
(This is the acceptance criterion "re-runnable without errors".)

### Step 5: Load the demo data (dev only)
1. Mark the database as development (one time):
   ```sql
   UPDATE financial_settings SET value = '"development"' WHERE setting_key = 'environment';
   ```
2. Run `database/seed_data/dev_seed_financial_phase1.sql`. Expected last result:

   | name | budget_status | approved_budget_total | contingency_now | ledger_rows |
   |---|---|---|---|---|
   | Demo · $100k Discovery Budget | baselined | 100000.00 | 6000.00 | 6 |
   | Demo · Land, Escrows & Property Tax | baselined | 475500.00 | 9000.00 | 1 |

3. See the discovery example in the ledger:
   ```sql
   SELECT l.entry_no, l.movement_type, l.amount, l.balance_after, l.reason
     FROM contingency_ledger l
     JOIN projects p ON p.id = l.project_id
    WHERE p.name = 'Demo · $100k Discovery Budget'
    ORDER BY l.entry_no;
   ```
   You should see 10,000 initial → −2,000 clearing overrun → +2,000 grading savings → −1,000 sewer overrun → −5,000 rock variance → +2,000 variance adjusted = **6,000**, while the total stays $100,000.

The demo users (`demo.*@example.test`) exist only in `public.users`. They cannot log in, and the Users page shows them as "pending". That is expected.

### Step 6: Check the existing app on dev
Nothing in the app reads the new tables yet. Spend five minutes clicking through:
log in → Users list (invite a test user) → Projects (open, edit a project) → a bid package → Awards → Milestones.
Everything should behave exactly as before. If you run the backend test suite, it should still pass:
```bash
cd backend && pytest
```

---

## 2. Production database

Do this only after section 1 is fully green and you are happy with dev.

### Step 1: Back up
- Supabase → **Database → Backups**. Confirm a recent daily backup exists, or Point-in-Time Recovery is enabled. Write down the time.
- Optional: take a schema + data dump of `public` with `pg_dump` from your machine.

### Step 2: Pick a quiet moment
The script needs a few seconds and only momentary locks on `users`, `projects`, `contracts` and `email_log`. No table is rewritten. If the app is busy, it fails fast after 5 seconds and changes nothing, and you can simply run it again.

### Step 3: Run the three files
1. `000_preflight_checks.sql`: everything `OK` / `INFO`, no `STOP`. Compare row 8 (email types) with dev; any extra value is fine because 001 keeps it.
2. `001_financial_foundation.sql`: "Success. No rows returned."
3. `002_verify_financial_foundation.sql`: all PASS. This is safe on production because it rolls back its own test data, and C99 proves it.

### Step 4: Do NOT
- run the seed file (it refuses anyway, because `environment` stays `"unset"` in production);
- run `099_rollback…` (see section 4).

### Step 5: Smoke test
Log in to the live app: dashboard, users list, a project, an award, milestones. Nothing should look different.

---

## 3. Working with the new data (until the Phase 2+ screens exist)

The admin screens for roles, budgets and approvals come with later phases. Meanwhile, use these statements in the SQL editor.

### Give someone a financial role
```sql
-- find ids
SELECT id, full_name, email, role FROM users WHERE is_active AND deleted_at IS NULL ORDER BY full_name;

-- grant (role: field_manager | executive | finance | project_manager | admin)
INSERT INTO user_roles (user_id, role, granted_by)
VALUES ('<user id>', 'executive', '<your user id>')
ON CONFLICT (user_id, role) WHERE revoked_at IS NULL DO NOTHING;

-- revoke (kept for audit)
UPDATE user_roles SET revoked_at = now(), revoked_by = '<your user id>'
 WHERE user_id = '<user id>' AND role = 'executive' AND revoked_at IS NULL;

-- who holds what
SELECT u.full_name, string_agg(ur.role, ', ' ORDER BY ur.role) AS roles, u.is_employee
  FROM users u JOIN user_roles ur ON ur.user_id = u.id AND ur.revoked_at IS NULL
 GROUP BY u.full_name, u.is_employee ORDER BY 1;
```
A person can hold several roles. For example, Kylie can be `executive` + `project_manager`.

### Reporting line, backup approver, limit, external flag
```sql
UPDATE users
   SET reports_to         = '<manager id>',
       backup_approver_id = '<backup id>',
       approval_limit     = 5000,      -- NULL = default from financial_settings
       is_employee        = TRUE       -- FALSE for external / temporary field managers
 WHERE id = '<field manager id>';
```

### Assign a manager and field manager to a project
```sql
UPDATE projects SET manager_id = '<manager id>', field_manager_id = '<field manager id>'
 WHERE id = '<project id>';
```

### Adjust settings (open questions from the plan)
```sql
SELECT setting_key, value, description FROM financial_settings ORDER BY 1;

UPDATE financial_settings SET value = '15'::jsonb,
       updated_by = '<your id>' WHERE setting_key = 'default_contingency_percent';
UPDATE financial_settings SET value = '["finance@example.com"]'::jsonb
 WHERE setting_key = 'finance_emails';
```

### Inviting a user with financial roles
The current Invite screen sends only `full_name` and `role`. The database already understands two extra keys (`roles`, `is_employee`), and the Phase 1.6 code change will add them to the screen. Until then, invite the person as usual and grant roles with the SQL above.

---

## 4. Rules the database now enforces (what errors mean)

| You try to… | Result |
|---|---|
| edit or delete a `contingency_ledger` row | `PT403` contingency_ledger is append-only |
| change a line amount after the budget is baselined (outside a procedure) | `PT409` amounts change only through financial procedures |
| change `contingency` directly | `PT409` |
| change `approved_budget_total` directly | `PT409`. Only an executive-approved top-up can. |
| a top-up approved by a non-executive | `PT403` |
| edit an approved or cancelled variance | `PT409`. Create a new variance. |
| approve a variance you created | check violation `chk_variance_lines_not_self_approved` |
| same person giving both payment approvals | check violation (two-person rule) |
| edit cash flow in a closed month, or reopen a month | `PT409` |
| close a month as non-finance / non-executive | `PT403` |
| create a variance on a project that is `on_hold` | `PT409` |

The backend maps `PT403 / PT404 / PT409 / PT422` to HTTP 403 / 404 / 409 / 422, the same as the existing milestone procedures.

---

## 5. Rollback

**Production:** the change is additive, and leaving the unused tables in place is harmless. If you truly need to undo it, restore the backup from section 2, step 1. Use `099` only after confirming no financial data needs keeping.

**Development** (to start over):
1. Open `099_rollback_financial_foundation.sql` and uncomment the first `SELECT set_config(...)` line.
2. Run the whole file. It drops all 19 tables and the new columns and restores the original invite trigger function. It also restores the original email CHECK, unless financial email types were already logged; in that case it keeps the wider CHECK. Bid-system data is left untouched, including the demo projects, tasks, vendor and users that the dev seed created in bid-system tables.
3. Re-run section 1 from Step 2.

---

## 6. What is NOT in this phase (by agreement)

- **No backend / frontend code** (Task 1.6 code part, deferred):
  - FastAPI: `roles[]` and `is_employee` on the invite request and in invite metadata; a `require_roles(...)` auth dependency reading `user_roles`; `roles` in `get_current_active_user`.
  - React: role multi-select and an external toggle in the Invite modal; `ProtectedRoute` role guards for finance screens; regenerate `database.types.ts`.
- **Storage:** the `finance-documents` private bucket (created with the invoice upload in Phase 2).
- **Back-fill** of budgets for active projects (Phase 12).
