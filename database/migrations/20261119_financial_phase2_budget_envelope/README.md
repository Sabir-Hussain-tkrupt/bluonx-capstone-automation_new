# Migration 20261119 — Phase 2 patch: budget envelope (schema v4.2)

Makes **Create budget** use real numbers from the project:

| Figure | Comes from |
|---|---|
| **Total budget** | The project's own **Budget** value (Overview / Edit project). If it is empty, the total is the sum of the lines, as before. |
| **Contingency** | Contingency % of the base, where base = total − land − contingency. In other words, contingency = (total − land) × % ÷ (100 + %). Example: $500,000 at 15% → $65,217.39. |
| **Committed** | Tasks that are already awarded come in at their **award amount**. An already-executed contract also locks the line and fills its dates. |
| **Unallocated budget** (new line) | Total − contingency − every other line, so the lines add up to the project budget. While the budget is a draft it absorbs every change to the other lines, so the total stays at the project budget. |
| **Remaining** | Project: total − contingency − committed. Line: budget − committed (none for the contingency line). |

Also new: **Reset draft budget** (`fn_reset_draft_budget`). It starts a draft over so it can be created again with these rules. Use it on drafts created before this patch.

| Order | File | Where |
|---|---|---|
| 1 | `001_budget_envelope.sql`: atomic, re-runnable | dev, then prod |
| 2 | `002_verify_budget_envelope.sql`: 14 checks, leaves no data | dev, then prod |
| — | `099_rollback_budget_envelope.sql` | dev only; afterwards re-run Phase 2's `001_budget_structure.sql` |

Requires Phase 1 and Phase 2. If Supabase shows the "destructive operations / RLS" warning, choose **Run without RLS**: no tables are created.

Note: re-running Phase 2's `001_budget_structure.sql` *after* this patch stops with "cannot drop columns from view" and changes nothing, so the patch can't be undone by accident.

Tested on PostgreSQL 15 (v3.9 + Phase 1 + Phase 2):
- applied twice;
- `002` gives 14/14 PASS, and Phase 2's verify still gives 29/29;
- rollback → Phase 2 re-apply → patch re-apply all pass;
- a fresh install from the master files is structurally identical to a migrated database.
