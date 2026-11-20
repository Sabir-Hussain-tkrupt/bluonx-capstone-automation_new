# Migration 20261121: Phase 3 contingency engine (schema v4.4)

| Task | Database change |
|---|---|
| **3.1 Contingency calculation** | While a budget is a **draft** (before bidding), contingency is recalculated whenever the base changes: land lines, the project Budget value or the project %. Formula: base = total − land − contingency, so contingency = (total − land) × % ÷ (100 + %). The Unallocated line absorbs the change, so the total stays at the project budget. `fn_set_project_contingency_percent` sets the project % (admin; refused after baseline). Default 15% comes from `financial_settings.default_contingency_percent` (Phase 1). |
| **3.2 Bid variance** | No change needed. Phase 1's `fn_apply_bid_to_line` already sets the line to the bid and moves the difference out of (overrun) or into (savings) contingency, with a ledger row. After baseline, line amounts can only change through procedures, so savings can't be moved to another line. |
| **3.3 Ledger view** | `v_contingency_ledger`: every movement with source line, direction (in/out), user, bucket kind and running balance. |
| **3.4 Bidding-complete checkpoint** | New project columns `bidding_completed_at / _by / _contingency_left_pct / _note`. `fn_complete_bidding` records the % of the base left. Below the target (10%) it writes a warning alert. At or below the escalation % (5%), or when contingency is negative, it writes a critical alert, and the app emails the executives and finance. At or above target nothing changes; contingency is never released early. `fn_reopen_bidding` is the admin undo. |
| **3.5 Top-ups** | `fn_approve_contingency_top_up` (still executive-only) now also raises the project's Budget value, so the project and the budget show the same total. Each top-up stays its own bucket and ledger row. |

| Order | File | Where |
|---|---|---|
| 1 | `001_contingency_engine.sql`: atomic, re-runnable | dev, then prod |
| 2 | `002_verify_contingency_engine.sql`: 10 checks, read-only | dev, then prod |
| 3 | `003_hotfix_private_grants.sql`: only if an earlier copy of 001 was already run (error "permission denied for function fin_recalc_draft_contingency") | where needed |
| — | `099_rollback_contingency_engine.sql` | dev only (drops the checkpoint columns) |

Requires Phase 1, Phase 2 and the 20261119 budget envelope patch. Adds no data; the only row it writes is the `schema_version` marker, like the earlier phases. If Supabase shows the "destructive operations / RLS" warning, choose **Run without RLS**: no tables are created.

## Settings (already present from Phase 1)

| Key | Default | Used for |
|---|---|---|
| `default_contingency_percent` | 15 | Contingency % when the project has none |
| `bidding_target_contingency_percent` | 10 | Target left after bidding |
| `bidding_escalation_percent` | 5 | At or below this the checkpoint escalates |
| `finance_emails` | [] | Emailed on approved top-ups and escalations, on top of users with the Finance role |
| `sales_emails` | [] | Emailed on approved top-ups |

Admins edit these on **Budget Templates → Contingency settings**.

## What the app does with it

- **Budget tab → Contingency panel:** starting amount, movements, remaining and % left of the base, plus per bucket (initial + each top-up) its starting, used, returned, remaining and %. Buttons: Change % (admin, draft only), View ledger, Request top-up (PM/admin), Mark bidding complete (PM/admin). Pending top-ups are listed with Review (executives) and Withdraw (requester/admin).
- **Contingency ledger** (Budget tab view): every movement, newest first, with amount, direction, balance after, bucket balance, source line, user and time. Export to CSV.
- **Mark bidding complete** lists competitive and direct-assign tasks still without an award (the PM must tick that they reviewed them), shows the % left against the target, and says whether it will escalate.
- **Top-up approval** is executive-only (checked in the API and in SQL). Approval adds the amount to contingency and to the total budget. Finance and sales are emailed; the requester gets an in-app notice.
- **Who gets notified:**
  - top-up requested: executives (in-app and email);
  - top-up decided: the requester (in-app); if approved, also finance and sales (email);
  - bidding escalated: executives and finance (in-app and email).
