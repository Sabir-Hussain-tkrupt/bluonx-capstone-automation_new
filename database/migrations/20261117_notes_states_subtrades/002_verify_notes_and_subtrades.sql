-- ============================================================================
-- BluOnX — Project notes, subtrades, safe trade delete
-- 002  VERIFY (self-checking, leaves NO data behind)
-- ============================================================================
-- Run AFTER 001_notes_and_subtrades.sql. Safe on production (rolls back).
-- Every row must say PASS (C10 may say SKIP if the editor cannot switch role).
-- ============================================================================

CREATE TEMP TABLE IF NOT EXISTS _verify_nst (seq INTEGER, check_id TEXT, result TEXT, detail TEXT);
TRUNCATE _verify_nst;

DO $verify$
DECLARE
  r        JSONB := '[]'::jsonb;
  n        INTEGER;
  v_txt    TEXT;
  v_json   JSONB;
  u        UUID := gen_random_uuid();
  p        UUID;
  t_parent UUID;
  t_sub    UUID;
  t_sub2   UUID;
  t_other  UUID;
  t_free   UUID;
  v_vendor UUID;
  v_task   UUID;
BEGIN
  BEGIN
    INSERT INTO public.users (id, email, full_name, role) VALUES (u, 'nst.' || u || '@example.test', 'NST Admin', 'admin');
    INSERT INTO public.projects (name, status, created_by) VALUES ('ZZ NST Project', 'active', u) RETURNING id INTO p;

    -- C01 notes table
    INSERT INTO public.project_notes (project_id, title, content_html, content_text, created_by)
    VALUES (p, 'Kick-off', '<p><strong>Bold</strong> and <em>italic</em></p>', 'Bold and italic', u);
    SELECT count(*) INTO n FROM public.project_notes WHERE project_id = p;
    r := r || jsonb_build_object('id','C01 project_notes stores a rich-text note','ok', n = 1, 'detail', n || ' note');

    -- C02 blank title refused
    BEGIN
      INSERT INTO public.project_notes (project_id, title, created_by) VALUES (p, '  ', u);
      r := r || jsonb_build_object('id','C02 note title cannot be blank','ok', false, 'detail', 'no error');
    EXCEPTION WHEN check_violation THEN
      r := r || jsonb_build_object('id','C02 note title cannot be blank','ok', true, 'detail', '23514');
    END;

    -- Trades
    INSERT INTO public.trades (name, phase) VALUES ('ZZ Electrical', 'development') RETURNING id INTO t_parent;
    INSERT INTO public.trades (name, phase, parent_trade_id) VALUES ('Commercial', 'due_diligence', t_parent) RETURNING id INTO t_sub;
    INSERT INTO public.trades (name, phase) VALUES ('ZZ Plumbing', 'development') RETURNING id INTO t_other;

    -- C03 subtrade inherits phase
    SELECT phase INTO v_txt FROM public.trades WHERE id = t_sub;
    r := r || jsonb_build_object('id','C03 subtrade takes its parent''s phase','ok', v_txt = 'development', 'detail', v_txt);

    -- C04 same subtrade name allowed under another trade; not twice under the same one
    INSERT INTO public.trades (name, phase, parent_trade_id) VALUES ('Commercial', 'development', t_other) RETURNING id INTO t_sub2;
    BEGIN
      INSERT INTO public.trades (name, phase, parent_trade_id) VALUES ('Commercial', 'development', t_parent);
      r := r || jsonb_build_object('id','C04 subtrade names unique per trade, reusable across trades','ok', false, 'detail', 'duplicate accepted');
    EXCEPTION WHEN unique_violation THEN
      r := r || jsonb_build_object('id','C04 subtrade names unique per trade, reusable across trades','ok', true, 'detail', '23505 on duplicate');
    END;

    -- C05 only one level
    BEGIN
      INSERT INTO public.trades (name, phase, parent_trade_id) VALUES ('Too deep', 'development', t_sub);
      r := r || jsonb_build_object('id','C05 a subtrade cannot have subtrades','ok', false, 'detail', 'no error');
    EXCEPTION WHEN SQLSTATE 'PT422' THEN
      r := r || jsonb_build_object('id','C05 a subtrade cannot have subtrades','ok', true, 'detail', 'PT422');
    END;

    -- C06 parent phase change flows down
    UPDATE public.trades SET phase = 'both' WHERE id = t_parent;
    SELECT phase INTO v_txt FROM public.trades WHERE id = t_sub;
    r := r || jsonb_build_object('id','C06 parent phase change updates its subtrades','ok', v_txt = 'both', 'detail', v_txt);

    -- C07 a trade with subtrades cannot be assigned directly
    INSERT INTO public.vendors (company_name) VALUES ('ZZ NST Vendor') RETURNING id INTO v_vendor;
    BEGIN
      INSERT INTO public.vendor_trades (vendor_id, trade_id) VALUES (v_vendor, t_parent);
      r := r || jsonb_build_object('id','C07 trade with subtrades must be assigned via a subtrade','ok', false, 'detail', 'no error');
    EXCEPTION WHEN SQLSTATE 'PT422' THEN
      INSERT INTO public.vendor_trades (vendor_id, trade_id) VALUES (v_vendor, t_sub);
      INSERT INTO public.tasks (project_id, trade_id, name, phase, bid_type, created_by)
        VALUES (p, t_sub, 'ZZ wiring', 'development', 'competitive', u) RETURNING id INTO v_task;
      r := r || jsonb_build_object('id','C07 trade with subtrades must be assigned via a subtrade','ok', true, 'detail', 'PT422 on parent, subtrade accepted');
    END;

    -- C08 usage counts
    v_json := public.fn_trade_usage(t_sub);
    r := r || jsonb_build_object('id','C08 usage counts tasks and vendors',
           'ok', (v_json ->> 'tasks')::int = 1 AND (v_json ->> 'vendors')::int = 1 AND (v_json ->> 'total')::int = 2,
           'detail', v_json::text);

    -- C09 delete blocked when in use / has subtrades; allowed when free
    BEGIN
      PERFORM public.fn_delete_trade(t_sub);
      r := r || jsonb_build_object('id','C09 used trade / trade with subtrades cannot be deleted; free one can','ok', false, 'detail', 'used subtrade deleted');
    EXCEPTION WHEN SQLSTATE 'PT409' THEN
      BEGIN
        PERFORM public.fn_delete_trade(t_other);   -- has a subtrade
        r := r || jsonb_build_object('id','C09 used trade / trade with subtrades cannot be deleted; free one can','ok', false, 'detail', 'parent with subtrade deleted');
      EXCEPTION WHEN SQLSTATE 'PT409' THEN
        PERFORM public.fn_delete_trade(t_sub2);    -- unused subtrade
        PERFORM public.fn_delete_trade(t_other);   -- now empty
        SELECT count(*) INTO n FROM public.trades WHERE id IN (t_sub2, t_other);
        r := r || jsonb_build_object('id','C09 used trade / trade with subtrades cannot be deleted; free one can','ok', n = 0, 'detail', 'PT409 ×2, then deleted');
      END;
    END;

    -- C10 RLS on notes
    BEGIN
      PERFORM set_config('request.jwt.claim.sub', u::text, TRUE);
      PERFORM set_config('request.jwt.claims', jsonb_build_object('sub', u)::text, TRUE);
      SET LOCAL ROLE authenticated;
      SELECT count(*) INTO n FROM public.project_notes WHERE project_id = p;
      BEGIN
        INSERT INTO public.project_notes (project_id, title, created_by) VALUES (p, 'sneaky', u);
        RESET ROLE;
        r := r || jsonb_build_object('id','C10 notes readable by active users, not writable directly','ok', false, 'detail', 'insert allowed');
      EXCEPTION WHEN insufficient_privilege THEN
        RESET ROLE;
        r := r || jsonb_build_object('id','C10 notes readable by active users, not writable directly','ok', n = 1, 'detail', 'read ' || n || ', write 42501');
      END;
    EXCEPTION WHEN OTHERS THEN
      RESET ROLE;
      r := r || jsonb_build_object('id','C10 notes readable by active users, not writable directly','ok', NULL, 'detail', 'SKIP: ' || SQLERRM);
    END;

    RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = '__verify_nst_rollback__';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> '__verify_nst_rollback__' THEN
      r := r || jsonb_build_object('id','ABORTED — unexpected error, later checks did not run','ok', false, 'detail', SQLSTATE || ': ' || SQLERRM);
    END IF;
  END;

  RESET ROLE;
  INSERT INTO _verify_nst (seq, check_id, result, detail)
  SELECT ord, e ->> 'id',
         CASE WHEN e -> 'ok' = 'null'::jsonb THEN 'SKIP' WHEN (e ->> 'ok')::boolean THEN 'PASS' ELSE 'FAIL' END,
         e ->> 'detail'
    FROM jsonb_array_elements(r) WITH ORDINALITY AS t(e, ord);
END
$verify$;

INSERT INTO _verify_nst
SELECT 999, 'C99 no verify data left behind',
       CASE WHEN (SELECT count(*) FROM public.projects WHERE name = 'ZZ NST Project') = 0 THEN 'PASS' ELSE 'FAIL' END,
       'rows: ' || (SELECT count(*) FROM public.projects WHERE name = 'ZZ NST Project');

SELECT seq, result, check_id, detail FROM _verify_nst ORDER BY seq;
