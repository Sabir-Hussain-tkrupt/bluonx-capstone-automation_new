# Migration 20261126: Phase 5 contingency health (schema v4.6)

Requires Phases 1–4. Run in the Supabase SQL editor. No new tables, so there is no RLS step.

| Order | File | Where |
|---|---|---|
| 1 | `001_contingency_health.sql`: atomic, re-runnable | dev, then prod |
| 2 | `002_verify_contingency_health.sql`: 10 checks, read-only | dev, then prod |
| — | `099_rollback_contingency_health.sql` | dev only |

Run 001 before starting the new backend. It retires the Phase 4 guardrail trigger, so if Phase 4's `002` is run again afterwards, its V03 and V09 checks report FAIL; that is expected. Do not re-run Phase 4's `001` after this one.
