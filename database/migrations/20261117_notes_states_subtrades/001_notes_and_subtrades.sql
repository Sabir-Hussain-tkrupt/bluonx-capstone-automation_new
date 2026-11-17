-- ============================================================================
-- BluOnX — Project notes, subtrades, safe trade delete
-- 001  SCHEMA CHANGE SCRIPT
-- ============================================================================
-- Version:  4.3.0
-- Date:     November 17, 2026
-- Requires: Bid Management schema v3.9 (works with or without the financial
--           module; budget tables are only counted when they exist)
-- ============================================================================
--
-- WHAT THIS SCRIPT DOES
--   1. project_notes — rich-text notes on a project (HTML from the editor +
--      a plain-text copy), soft-deleted, read by any active user.
--   2. Subtrades — trades.parent_trade_id (one level: trade → subtrade).
--      • a subtrade inherits its parent's phase (kept in step automatically)
--      • trade names are unique among top-level trades, and subtrade names are
--        unique within their parent (the old global UNIQUE(name) is replaced,
--        so two trades may each have e.g. a "Commercial" subtrade)
--      • a trade that HAS subtrades cannot be assigned directly to a task,
--        vendor, task template or bid template — one of its subtrades must be
--        chosen (enforced by trigger on new / changed assignments only;
--        existing rows are never touched)
--   3. fn_trade_usage / fn_delete_trade — a trade or subtrade can be deleted
--      only when nothing uses it (tasks, vendors, task / bid / budget
--      templates, variances) and it has no subtrades.
--
-- No US-state change is needed: the Projects / Vendors state filters use the
-- existing projects.state / vendors.state columns.
--
-- SAFETY: additive, idempotent, one transaction. The only in-place change is
-- replacing UNIQUE(trades.name) with two narrower unique indexes that every
-- existing row already satisfies (they allow strictly more, never less).
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';


-- ============================================================================
-- SECTION A: project_notes
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.project_notes (
  id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id    UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  title         VARCHAR(255)  NOT NULL CHECK (btrim(title) <> ''),
  content_html  TEXT          NOT NULL DEFAULT '',
  content_text  TEXT          NOT NULL DEFAULT '',
  created_by    UUID          NOT NULL REFERENCES public.users(id) ON DELETE RESTRICT,
  updated_by    UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at    TIMESTAMPTZ,

  -- Document-sized notes are fine; this only stops a runaway paste (~2 MB).
  CONSTRAINT chk_project_notes_size CHECK (length(content_html) <= 2000000)
);

CREATE INDEX IF NOT EXISTS idx_project_notes_project
  ON public.project_notes (project_id, updated_at DESC) WHERE deleted_at IS NULL;

COMMENT ON TABLE  public.project_notes              IS 'Free-form rich-text notes on a project (meeting notes, site observations, decisions). Written through FastAPI; any active user reads. Soft-deleted.';
COMMENT ON COLUMN public.project_notes.content_html IS 'Rich text as HTML produced by the editor (bold, italic, headings, lists, links …). Rendered back through the same editor schema, never injected as raw HTML.';
COMMENT ON COLUMN public.project_notes.content_text IS 'Plain-text copy of the note for previews and search.';
COMMENT ON COLUMN public.project_notes.deleted_at   IS 'Soft delete. NULL = visible.';

DROP TRIGGER IF EXISTS trg_project_notes_updated_at ON public.project_notes;
CREATE TRIGGER trg_project_notes_updated_at
  BEFORE UPDATE ON public.project_notes FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

ALTER TABLE public.project_notes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.project_notes FROM anon;
REVOKE ALL ON TABLE public.project_notes FROM authenticated;
GRANT SELECT ON TABLE public.project_notes TO authenticated;
GRANT ALL ON TABLE public.project_notes TO service_role;

DROP POLICY IF EXISTS project_notes_select_authenticated ON public.project_notes;
CREATE POLICY project_notes_select_authenticated
  ON public.project_notes FOR SELECT TO authenticated
  USING ((SELECT private.is_active_user()) AND deleted_at IS NULL);


-- ============================================================================
-- SECTION B: Subtrades
-- ============================================================================

ALTER TABLE public.trades ADD COLUMN IF NOT EXISTS parent_trade_id UUID;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_trades_parent') THEN
    ALTER TABLE public.trades ADD CONSTRAINT fk_trades_parent
      FOREIGN KEY (parent_trade_id) REFERENCES public.trades(id) ON DELETE RESTRICT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_trades_parent_not_self') THEN
    ALTER TABLE public.trades ADD CONSTRAINT chk_trades_parent_not_self
      CHECK (parent_trade_id IS NULL OR parent_trade_id <> id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_trades_parent ON public.trades (parent_trade_id) WHERE parent_trade_id IS NOT NULL;

COMMENT ON COLUMN public.trades.parent_trade_id IS
  'NULL = top-level trade. Set = subtrade of that trade (one level only). A subtrade inherits its parent''s phase. A trade that has subtrades must be assigned through one of them.';

-- Names: unique among top-level trades, and within each parent.
DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT conname FROM pg_constraint
     WHERE conrelid = 'public.trades'::regclass AND contype = 'u'
       AND pg_get_constraintdef(oid) = 'UNIQUE (name)'
  LOOP
    EXECUTE format('ALTER TABLE public.trades DROP CONSTRAINT %I', r.conname);
  END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_top_level_name
  ON public.trades (name) WHERE parent_trade_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_trades_subtrade_name
  ON public.trades (parent_trade_id, name) WHERE parent_trade_id IS NOT NULL;


-- B.1 One level only; a subtrade takes its parent's phase.
CREATE OR REPLACE FUNCTION public.fn_trades_hierarchy()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_parent public.trades;
BEGIN
  IF NEW.parent_trade_id IS NULL THEN
    RETURN NEW;
  END IF;

  SELECT * INTO v_parent FROM public.trades WHERE id = NEW.parent_trade_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Parent trade % not found', NEW.parent_trade_id USING ERRCODE = 'PT404';
  END IF;
  IF v_parent.parent_trade_id IS NOT NULL THEN
    RAISE EXCEPTION 'Subtrades cannot have their own subtrades ("%" is already a subtrade).', v_parent.name
      USING ERRCODE = 'PT422';
  END IF;
  IF TG_OP = 'UPDATE' AND EXISTS (SELECT 1 FROM public.trades WHERE parent_trade_id = NEW.id) THEN
    RAISE EXCEPTION 'Trade "%" has subtrades, so it cannot become a subtrade itself.', NEW.name
      USING ERRCODE = 'PT422';
  END IF;

  NEW.phase := v_parent.phase;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_trades_hierarchy ON public.trades;
CREATE TRIGGER trg_trades_hierarchy
  BEFORE INSERT OR UPDATE OF parent_trade_id, phase ON public.trades
  FOR EACH ROW EXECUTE FUNCTION public.fn_trades_hierarchy();

-- B.2 Parent phase change flows down to its subtrades.
CREATE OR REPLACE FUNCTION public.fn_trades_cascade_phase()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  IF NEW.parent_trade_id IS NULL AND NEW.phase IS DISTINCT FROM OLD.phase THEN
    UPDATE public.trades SET phase = NEW.phase WHERE parent_trade_id = NEW.id AND phase <> NEW.phase;
  END IF;
  RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS trg_trades_cascade_phase ON public.trades;
CREATE TRIGGER trg_trades_cascade_phase
  AFTER UPDATE OF phase ON public.trades
  FOR EACH ROW EXECUTE FUNCTION public.fn_trades_cascade_phase();


-- B.3 A trade with subtrades must be assigned through a subtrade.
--     Fires only when trade_id is set or changed, so existing rows that point
--     at a trade which later gets subtrades are never blocked.
CREATE OR REPLACE FUNCTION public.fn_enforce_leaf_trade()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_name TEXT;
BEGIN
  IF NEW.trade_id IS NULL THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.trade_id IS NOT DISTINCT FROM OLD.trade_id THEN
    RETURN NEW;
  END IF;
  IF EXISTS (SELECT 1 FROM public.trades WHERE parent_trade_id = NEW.trade_id AND is_active) THEN
    SELECT name INTO v_name FROM public.trades WHERE id = NEW.trade_id;
    RAISE EXCEPTION 'Trade "%" has subtrades — choose one of its subtrades.', v_name
      USING ERRCODE = 'PT422';
  END IF;
  RETURN NEW;
END;
$$;

COMMENT ON FUNCTION public.fn_enforce_leaf_trade() IS
  'Blocks assigning a trade that has active subtrades (one of the subtrades must be chosen). Attached to tasks, vendor_trades, task_templates and bid_templates; only fires when trade_id is set or changed.';

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['tasks', 'vendor_trades', 'task_templates', 'bid_templates'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I', 'trg_' || t || '_leaf_trade', t);
      EXECUTE format(
        'CREATE TRIGGER %I BEFORE INSERT OR UPDATE OF trade_id ON public.%I FOR EACH ROW EXECUTE FUNCTION public.fn_enforce_leaf_trade()',
        'trg_' || t || '_leaf_trade', t);
    END IF;
  END LOOP;
END $$;


-- ============================================================================
-- SECTION C: Trade usage + safe delete
-- ============================================================================

-- C.1 How many records use a trade (counted directly, not through subtrades).
CREATE OR REPLACE FUNCTION public.fn_trade_usage(p_trade_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SET search_path = ''
AS $$
DECLARE
  v_result JSONB := '{}'::jsonb;
  v_n      BIGINT;
  v_total  BIGINT := 0;
  r        RECORD;
BEGIN
  FOR r IN
    SELECT * FROM (VALUES
      ('tasks',                 'tasks',                 'trade_id'),
      ('vendors',               'vendor_trades',         'trade_id'),
      ('task_templates',        'task_templates',        'trade_id'),
      ('bid_templates',         'bid_templates',         'trade_id'),
      ('budget_template_lines', 'budget_template_lines', 'trade_id'),
      ('variances',             'variance_lines',        'trade_id'),
      ('subtrades',             'trades',                'parent_trade_id')
    ) AS x(label, tbl, col)
  LOOP
    IF to_regclass('public.' || r.tbl) IS NULL THEN
      v_n := 0;
    ELSE
      EXECUTE format('SELECT count(*) FROM public.%I WHERE %I = $1', r.tbl, r.col) INTO v_n USING p_trade_id;
    END IF;
    v_result := v_result || jsonb_build_object(r.label, v_n);
    v_total := v_total + v_n;
  END LOOP;
  RETURN v_result || jsonb_build_object('total', v_total);
END;
$$;

COMMENT ON FUNCTION public.fn_trade_usage(UUID) IS
  'Counts every record that references a trade: tasks (including deleted ones — they still hold the reference), vendors, task / bid / budget templates, variances, and its subtrades. total = 0 means it can be edited or deleted.';


-- C.2 Delete a trade or subtrade only when nothing uses it.
CREATE OR REPLACE FUNCTION public.fn_delete_trade(p_trade_id UUID)
RETURNS SETOF public.trades
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_trade public.trades;
  v_usage JSONB;
  v_parts TEXT;
BEGIN
  SELECT * INTO v_trade FROM public.trades WHERE id = p_trade_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Trade % not found', p_trade_id USING ERRCODE = 'PT404';
  END IF;

  v_usage := public.fn_trade_usage(p_trade_id);
  IF (v_usage ->> 'total')::bigint > 0 THEN
    SELECT string_agg(value || ' ' || replace(key, '_', ' '), ', ' ORDER BY key) INTO v_parts
      FROM jsonb_each_text(v_usage)
     WHERE key <> 'total' AND value::bigint > 0;
    RAISE EXCEPTION '"%" cannot be deleted because it is in use (%).', v_trade.name, v_parts
      USING ERRCODE = 'PT409';
  END IF;

  DELETE FROM public.trades WHERE id = p_trade_id;
  RETURN NEXT v_trade;
END;
$$;

COMMENT ON FUNCTION public.fn_delete_trade(UUID) IS
  'Hard-deletes a trade or subtrade, row-locked, only when fn_trade_usage reports nothing using it (no tasks, vendors, templates, variances or subtrades). PT409 with the usage otherwise.';

REVOKE ALL ON FUNCTION public.fn_trade_usage(uuid)  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_delete_trade(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_trade_usage(uuid)  TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_delete_trade(uuid) TO service_role;
REVOKE ALL ON FUNCTION public.fn_trades_hierarchy()     FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_trades_cascade_phase() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_enforce_leaf_trade()   FROM PUBLIC, anon, authenticated;

COMMIT;
