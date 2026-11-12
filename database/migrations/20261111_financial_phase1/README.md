# Migration 20261111 — Financial Automation Phase 1 foundation (schema v4.0)

Adds the financial module (19 tables, procedures, guards, RLS) on top of the
live Bid Management schema v3.9. **Additive only**: no existing data or object
is removed or rewritten.

| Order | File | Changes data? | Where |
|---|---|---|---|
| 1 | `000_preflight_checks.sql` | No (read-only) | dev, then prod |
| 2 | `001_financial_foundation.sql` | Yes: schema only, atomic, re-runnable | dev, then prod |
| 3 | `002_verify_financial_foundation.sql` | No (test data is rolled back) | dev, then prod |
| — | `../../seed_data/dev_seed_financial_phase1.sql` | Yes: demo data | **dev only** |
| — | `099_rollback_financial_foundation.sql` | Yes: drops the financial module | dev only (needs explicit confirmation) |

Expected results:
- `000`: every row is `OK` or `INFO`, and no row is `STOP`.
- `001`: "Success. No rows returned".
- `002`: 35 rows, all `PASS`. `SKIP` is acceptable only for C08 and C33.

Full step-by-step guide: [`docs/financial/PHASE1_RUNBOOK.md`](../../../docs/financial/PHASE1_RUNBOOK.md).

Tested on PostgreSQL 15 against the v3.9 master schema:
- fresh v3.9 + `001` twice → `002` 35/35 PASS;
- seed → existing flows (project edit, invite, role toggle, awards, milestones, contract complete) unchanged;
- `099` → schema identical to v3.9;
- fresh install from the updated master files → schema identical to a migrated database.
