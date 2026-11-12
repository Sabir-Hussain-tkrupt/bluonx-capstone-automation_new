# Migration 20261118 — Financial Automation Phase 2: project budget structure (schema v4.1)

Adds the budget engine on top of Phase 1 (v4.0):
- the default standard template;
- the procedures `fn_create_project_budget`, `fn_reorder_budget_lines`, `fn_remove_budget_line`, `fn_apply_budget_import` and `fn_categorise_internal_invoice`;
- the task → budget line sync trigger;
- the `v_budget_lines` / `v_project_budget_summary` views;
- the private `finance-documents` storage bucket.

**Additive only.** No existing function or table changes. The task trigger does nothing for projects without a budget, which is every project until an admin creates one.

| Order | File | Changes data? | Where |
|---|---|---|---|
| 1 | `000_preflight_checks.sql` | No (read-only) | dev, then prod |
| 2 | `001_budget_structure.sql` | Yes: schema, default template, bucket. Atomic and re-runnable. | dev, then prod |
| 3 | `002_verify_budget_structure.sql` | No (test data is rolled back) | dev, then prod |
| — | `../../seed_data/dev_seed_financial_phase2.sql` | Yes: demo data | **dev only** |
| — | `099_rollback_budget_structure.sql` | Removes Phase 2 objects (data kept) | dev only (needs explicit confirmation) |

Expected results:
- `000`: everything `OK` / `INFO`.
- `001`: "Success. No rows returned".
- `002`: 29 rows, all `PASS`. A `SKIP` on C28 only means the editor could not switch role.

If Supabase shows the "destructive operations / RLS" warning when running `001`, choose **Run without RLS**. The file only drops-and-recreates its own trigger, and it creates no tables.

There are no new RLS policies: the two views are `security_invoker`, so the Phase 1 table policies apply. Invoice totals reach every role through a `SECURITY DEFINER` sum, so totals look the same to everyone, while the invoice rows themselves stay finance-only.

Tested on PostgreSQL 15 with the v3.9 schema plus Phase 1:
- `001` applied twice → `002` gives 29/29 PASS;
- `099` → re-apply → 29/29 PASS;
- a fresh install from the updated master files gives a schema identical to a migrated database;
- the dev seed runs and re-runs cleanly.
