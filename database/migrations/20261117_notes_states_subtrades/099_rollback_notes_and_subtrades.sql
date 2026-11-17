-- ============================================================================
-- BluOnX — Project notes, subtrades, safe trade delete
-- 099  ROLLBACK  (DEV / TEST DATABASES ONLY)
-- ============================================================================
-- Undoes 001_notes_and_subtrades.sql.
--   • project_notes is DROPPED (its notes are lost).
--   • Subtrades are refused while any exist: delete or re-point them first,
--     because the old UNIQUE(name) rule cannot hold names reused across trades.
-- ============================================================================

BEGIN;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema = 'public' AND table_name = 'trades' AND column_name = 'parent_trade_id')
     AND EXISTS (SELECT 1 FROM public.trades WHERE parent_trade_id IS NOT NULL) THEN
    RAISE EXCEPTION 'Rollback stopped: subtrades exist. Delete them (or clear parent_trade_id) first.';
  END IF;
END $$;

-- Leaf-trade triggers
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['tasks', 'vendor_trades', 'task_templates', 'bid_templates'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('DROP TRIGGER IF EXISTS %I ON public.%I', 'trg_' || t || '_leaf_trade', t);
    END IF;
  END LOOP;
END $$;

DROP TRIGGER IF EXISTS trg_trades_hierarchy     ON public.trades;
DROP TRIGGER IF EXISTS trg_trades_cascade_phase ON public.trades;

DROP FUNCTION IF EXISTS public.fn_delete_trade(uuid);
DROP FUNCTION IF EXISTS public.fn_trade_usage(uuid);
DROP FUNCTION IF EXISTS public.fn_enforce_leaf_trade();
DROP FUNCTION IF EXISTS public.fn_trades_cascade_phase();
DROP FUNCTION IF EXISTS public.fn_trades_hierarchy();

DROP INDEX IF EXISTS public.uq_trades_subtrade_name;
DROP INDEX IF EXISTS public.uq_trades_top_level_name;
DROP INDEX IF EXISTS public.idx_trades_parent;

ALTER TABLE public.trades DROP CONSTRAINT IF EXISTS chk_trades_parent_not_self;
ALTER TABLE public.trades DROP CONSTRAINT IF EXISTS fk_trades_parent;
ALTER TABLE public.trades DROP COLUMN IF EXISTS parent_trade_id;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                  WHERE conrelid = 'public.trades'::regclass AND contype = 'u'
                    AND pg_get_constraintdef(oid) = 'UNIQUE (name)') THEN
    ALTER TABLE public.trades ADD CONSTRAINT trades_name_key UNIQUE (name);
  END IF;
END $$;

DROP TABLE IF EXISTS public.project_notes;

COMMIT;
