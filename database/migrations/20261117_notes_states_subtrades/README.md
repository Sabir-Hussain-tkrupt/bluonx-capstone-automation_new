# Migration 20261117: project notes, subtrades, safe trade delete (schema v4.3)

| Feature | Database change |
|---|---|
| **Project notes** (rich text, document-sized) | New table `project_notes`: title, editor HTML, plain-text copy, author, soft delete. Any active user reads it (RLS); writes go through the API. |
| **Subtrades** | `trades.parent_trade_id` (one level: trade → subtrade). A subtrade always has its parent's phase. Names must be unique among trades and within each trade, so two trades may each have a "Commercial" subtrade. |
| **"Choose a subtrade"** | Trigger on `tasks`, `vendor_trades`, `task_templates` and `bid_templates`: a trade that has subtrades cannot be assigned directly. The trigger only fires when `trade_id` is set or changed, so existing rows are never blocked. |
| **Safe edit / delete** | `fn_trade_usage(trade)` counts tasks, vendors, task / bid / budget templates, variances and subtrades. `fn_delete_trade(trade)` deletes only when that count is 0. |
| **US state filters** (Projects, Vendors) | None. They use the existing `state` columns. |

| Order | File | Where |
|---|---|---|
| 1 | `001_notes_and_subtrades.sql`: atomic, re-runnable | dev, then prod |
| 2 | `002_verify_notes_and_subtrades.sql`: 10 checks + cleanup check, leaves no data | dev, then prod |
| — | `099_rollback_notes_and_subtrades.sql` | dev only (drops `project_notes`; refused while subtrades exist) |

Independent of the financial migrations: it can run before or after them. Budget template lines and variances are counted only when those tables exist.

If Supabase shows the "destructive operations / RLS" warning, choose **Run without RLS**. The script enables RLS and adds the read policy itself. The warning appears because the old `UNIQUE (name)` constraint on `trades` is replaced by two narrower unique indexes, which every existing row already satisfies.

## What the app does with it

- **Project → Notes tab → + Add Note.** A title plus a document editor with headings, bold, italic, underline, strike, lists, quote, code block, divider, link, alignment, undo / redo and a word count. Notes can be any length (up to about 2 million characters of formatted text). The author or an admin can edit or delete a note. On archived projects notes are read-only.
- **Settings → Trades.** Each trade's ⋯ menu offers **Add subtrade**, **Edit** and **Delete**. Edit and Delete first check usage. A trade that is in use cannot be renamed or deleted, and the dialog says what uses it (for example "3 tasks and 1 vendor"). A trade that still has subtrades cannot be deleted until its subtrades are removed.
- **Trade pickers** (task, task template, bid template, budget template line, vendor trades) list "Electrical › Commercial" for subtrades. A trade that has subtrades cannot be picked on its own.
- **Vendor matching for bids**: a task on "Electrical › Commercial" also finds vendors registered for "Electrical" as a whole, and an older task on "Electrical" finds vendors of any Electrical subtrade.
- **Filters**: "Electrical (all)" in a trade filter also lists the subtrades' records. The Projects and Vendors lists have a **State** filter (all 50 states + DC) that matches a code ("MO") or a full name ("Missouri").
- **Budget Templates** moved from Settings to the sidebar, below Task Templates (admins). The old address redirects.

## Tested on PostgreSQL 15

- 001 applied twice on a migrated database (v3.9 + Phase 1 + Phase 2 + envelope patch);
- `002` gives 11/11 PASS;
- rollback → re-apply → verify passes;
- a fresh install from `bluonx_complete_schema.sql` + `rls_policies.sql` matches a migrated database for every new object: columns, constraints, indexes, triggers, functions, policy and grants.
