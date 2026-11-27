# Migration 20261128: Phase 7 long-tail items, escrows and property taxes (schema v4.8)

Requires Phases 1–6. Run in the Supabase SQL editor. If Supabase warns about RLS, choose **Run without RLS**: the script enables RLS on the new tables itself.

| Order | File | Where |
|---|---|---|
| 1 | `001_long_tail.sql`: atomic, re-runnable | dev, then prod |
| 2 | `002_verify_long_tail.sql`: 8 checks, read-only | dev, then prod |
| — | `099_rollback_long_tail.sql` | dev only |

Bond documents go to the existing `finance-documents` bucket under `{project}/escrows/`.
