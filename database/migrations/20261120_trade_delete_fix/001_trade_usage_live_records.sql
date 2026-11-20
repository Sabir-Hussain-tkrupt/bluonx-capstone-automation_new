-- ============================================================================
-- BluOnX — Trade delete fix: count only live records
-- 001  SCHEMA CHANGE SCRIPT (functions only, no data, no table changes)
-- ============================================================================
-- Date:     November 20, 2026
-- Requires: 20261117_notes_states_subtrades/001_notes_and_subtrades.sql
-- ============================================================================
--
-- PROBLEM
--   After a vendor or project (with its tasks) was removed, its trade / subtrade
--   still showed "used by 1 vendor and 1 task" and could not be deleted.
--   Removed records are soft-deleted (deleted_at set): the rows stay, and
--   fn_trade_usage counted them.
--
-- FIX
--   1. fn_trade_usage counts only live records:
--        tasks           not deleted, in a project that is not deleted
--        vendors         not deleted
--        task templates  not deleted
--        bid templates, budget template lines, variances   (no soft delete)
--        subtrades       active only
--   2. fn_delete_trade, when nothing live uses the trade:
--        • nothing references it at all  -> hard delete (as before)
--        • only removed records still reference it (the database keeps those
--          references) -> the trade is retired instead: is_active = false and
--          its name gets a " [removed xxxxxxxx]" suffix, so it disappears from
--          every list and the name is free to be created again.
--
-- SAFETY: CREATE OR REPLACE of two functions, one transaction, re-runnable.
--         No table, column, policy or data change.
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';


-- 1. Usage: live records only ------------------------------------------------
CREATE OR REPLACE FUNCTION public.fn_trade_usage(p_trade_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
SET search_path = ''
AS $$
DECLARE
  v_tasks          BIGINT := 0;
  v_vendors        BIGINT := 0;
  v_task_templates BIGINT := 0;
  v_bid_templates  BIGINT := 0;
  v_budget_lines   BIGINT := 0;
  v_variances      BIGINT := 0;
  v_subtrades      BIGINT := 0;
BEGIN
  SELECT count(*) INTO v_tasks
    FROM public.tasks t
    JOIN public.projects p ON p.id = t.project_id
   WHERE t.trade_id = p_trade_id
     AND t.deleted_at IS NULL
     AND p.deleted_at IS NULL;

  SELECT count(*) INTO v_vendors
    FROM public.vendor_trades vt
    JOIN public.vendors v ON v.id = vt.vendor_id
   WHERE vt.trade_id = p_trade_id
     AND v.deleted_at IS NULL;

  SELECT count(*) INTO v_task_templates
    FROM public.task_templates
   WHERE trade_id = p_trade_id
     AND deleted_at IS NULL;

  SELECT count(*) INTO v_bid_templates
    FROM public.bid_templates
   WHERE trade_id = p_trade_id;

  -- Financial module tables: counted only when they exist.
  IF to_regclass('public.budget_template_lines') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.budget_template_lines WHERE trade_id = $1'
      INTO v_budget_lines USING p_trade_id;
  END IF;
  IF to_regclass('public.variance_lines') IS NOT NULL THEN
    EXECUTE 'SELECT count(*) FROM public.variance_lines WHERE trade_id = $1'
      INTO v_variances USING p_trade_id;
  END IF;

  SELECT count(*) INTO v_subtrades
    FROM public.trades
   WHERE parent_trade_id = p_trade_id
     AND is_active;

  RETURN jsonb_build_object(
    'tasks',                 v_tasks,
    'vendors',               v_vendors,
    'task_templates',        v_task_templates,
    'bid_templates',         v_bid_templates,
    'budget_template_lines', v_budget_lines,
    'variances',             v_variances,
    'subtrades',             v_subtrades,
    'total', v_tasks + v_vendors + v_task_templates + v_bid_templates
             + v_budget_lines + v_variances + v_subtrades
  );
END;
$$;

COMMENT ON FUNCTION public.fn_trade_usage(UUID) IS
  'Counts the live records that use a trade: tasks (not deleted, in a project that is not deleted), vendors (not deleted), task templates (not deleted), bid / budget templates, variances, and its active subtrades. Removed records are not counted. total = 0 means it can be edited or deleted.';


-- 2. Delete: hard delete, or retire when only removed records point at it ----
CREATE OR REPLACE FUNCTION public.fn_delete_trade(p_trade_id UUID)
RETURNS SETOF public.trades
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_trade public.trades;
  v_usage JSONB;
  v_parts TEXT;
  v_tag   TEXT;
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

  BEGIN
    DELETE FROM public.trades WHERE id = p_trade_id;
  EXCEPTION WHEN foreign_key_violation THEN
    -- Only removed records (deleted tasks / vendors / templates, retired
    -- subtrades) still reference it. Retire it: hidden everywhere, name freed.
    v_tag := ' [removed ' || left(p_trade_id::text, 8) || ']';
    UPDATE public.trades
       SET is_active = false,
           name      = left(name, 100 - length(v_tag)) || v_tag
     WHERE id = p_trade_id
     RETURNING * INTO v_trade;
  END;

  RETURN NEXT v_trade;
END;
$$;

COMMENT ON FUNCTION public.fn_delete_trade(UUID) IS
  'Deletes a trade or subtrade, row-locked, only when fn_trade_usage reports no live use (PT409 with the usage otherwise). Hard-deletes it when nothing references it; when only removed records still do, retires it instead (is_active = false, name suffixed " [removed xxxxxxxx]" so the name can be reused).';

REVOKE ALL ON FUNCTION public.fn_trade_usage(uuid)  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_delete_trade(uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_trade_usage(uuid)  TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_delete_trade(uuid) TO service_role;

COMMIT;
