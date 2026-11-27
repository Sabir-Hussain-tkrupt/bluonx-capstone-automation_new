# Migration 20261127: Phase 6 payment approvals and finance hand-off (schema v4.7)

Requires Phases 1–5. Run in the Supabase SQL editor. If Supabase warns about RLS, choose **Run without RLS**: the script enables RLS on the new table itself.

| Order | File | Where |
|---|---|---|
| 1 | `001_payment_approvals.sql`: atomic, re-runnable | dev, then prod |
| 2 | `002_verify_payment_approvals.sql`: 9 checks, read-only | dev, then prod |
| — | `099_rollback_payment_approvals.sql` | dev only (drops the payment history) |

The `finance-documents` storage bucket (Phase 2) holds the PO PDFs under `{project}/po/`.
