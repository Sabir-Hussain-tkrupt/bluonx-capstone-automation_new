# Migration 20261125: Phase 4 variance line management (schema v4.5)

Requires Phases 1–3. Run in the Supabase SQL editor. If Supabase warns about RLS, choose **Run without RLS**: the script enables RLS on the new table itself.

| Order | File | Where |
|---|---|---|
| 1 | `001_variance_management.sql`: atomic, re-runnable | dev, then prod |
| 2 | `002_verify_variance_management.sql`: 9 checks, read-only | dev, then prod |
| — | `099_rollback_variance_management.sql` | dev only (drops the variance history) |

| Task | Database change |
|---|---|
| **4.1 Create** | Reuses Phase 1 `fn_create_variance`. |
| **4.2 Deduct / adjust** | `fn_adjust_variance` extended (history, approval restart, 422s); new `fn_edit_variance`. A trigger on `contingency_ledger` recalculates the near-zero and negative contingency alerts after every movement. |
| **4.3 Approval** | `fn_approve_variance`, `fn_reject_variance`, `private.fin_route_manager`; each variance has its own `payment_approvals` row. |
| **4.4 UI reads** | New table `variance_events` (append-only) and view `v_variances`. |
| **4.5 Locks** | `fn_guard_budget_lines`, `fn_guard_variance_lines`, `fn_apply_bid_to_line` now answer PT422 for locked bids and approved variances. |

Data written: one "created" history event for each variance that already exists, and the `schema_version` marker.
