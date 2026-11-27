-- ============================================================================
-- BluOnX Financial Automation — Phase 7 · Module 7
-- 001  LONG-TAIL ITEMS: ESCROWS & PROPERTY TAXES (schema change script)
-- ============================================================================
-- Version:  4.8.0
-- Date:     November 28, 2026
-- Requires: Phases 1-6 (last: 20261127_financial_phase6_payments)
-- Engine:   PostgreSQL 15+ (Supabase)
-- ============================================================================
--
-- WHAT THIS SCRIPT DOES
--   7.1 jurisdictions (per city / county: repair estimate %, tax instalments,
--       reminder lead time). More escrow columns.
--   7.2 fn_create_escrow creates the escrow and its two cost lines (premium,
--       repairs to city standard) at the bottom of the budget.
--   7.3 fn_escrow_transition (posted → works built → inspection → corrections
--       → signed off → released), escrow_defects, bond renewals, escrow_events.
--   7.4 fn_set_property_tax_year: one budget line per tax year, instalments on
--       the jurisdiction's due dates, estimate from last year / assessed value /
--       finance, reduced for the sold portion.
--   Long-tail lines move money in a flat way: first from the template's
--   placeholder line of the same kind, then from contingency (baselined, with a
--   ledger row). Cash flow is refreshed from the escrows and taxes.
--
-- SAFETY: additive / CREATE OR REPLACE, idempotent, one transaction. Widens the
-- contingency_ledger movement_type CHECK. Rows written: settings and the
-- schema_version marker.
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $$
BEGIN
  IF to_regprocedure('public.fn_payment_approval_step(uuid, uuid, text, text, text, uuid, text, boolean)') IS NULL THEN
    RAISE EXCEPTION 'Phases 1 to 6 must be applied first.';
  END IF;
END $$;

-- ============================================================================
-- SECTION A: TABLES AND COLUMNS
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.jurisdictions (
  id                       UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  name                     VARCHAR(150)  NOT NULL CHECK (btrim(name) <> ''),
  kind                     VARCHAR(10)   NOT NULL DEFAULT 'city' CHECK (kind IN ('city', 'county', 'hoa', 'other')),
  state                    VARCHAR(50),
  repair_estimate_percent  DECIMAL(5,2)  CHECK (repair_estimate_percent IS NULL OR repair_estimate_percent BETWEEN 0 AND 100),
  tax_installments         JSONB         NOT NULL DEFAULT '[{"month": 12, "day": 31}]'::jsonb,
  reminder_days_before     INTEGER       NOT NULL DEFAULT 30 CHECK (reminder_days_before BETWEEN 1 AND 180),
  notes                    TEXT,
  created_by               UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  deleted_at               TIMESTAMPTZ,
  CONSTRAINT chk_jurisdictions_installments CHECK (jsonb_typeof(tax_installments) = 'array' AND jsonb_array_length(tax_installments) BETWEEN 1 AND 12)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_jurisdictions_name ON public.jurisdictions (lower(name), kind, COALESCE(state, '')) WHERE deleted_at IS NULL;

COMMENT ON TABLE public.jurisdictions IS
  'Cities / counties / HOAs. Standards vary, so each holds its own repair estimate % (escrow repairs to city standard), property tax instalment dates [{month, day}] and reminder lead time.';

DROP TRIGGER IF EXISTS trg_jurisdictions_updated_at ON public.jurisdictions;
CREATE TRIGGER trg_jurisdictions_updated_at BEFORE UPDATE ON public.jurisdictions
  FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS jurisdiction_id        UUID REFERENCES public.jurisdictions(id) ON DELETE RESTRICT;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS repair_estimate        DECIMAL(15,2) NOT NULL DEFAULT 0 CHECK (repair_estimate >= 0);
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS premium_frequency      VARCHAR(10) NOT NULL DEFAULT 'one_time' CHECK (premium_frequency IN ('one_time', 'yearly'));
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS premium_total          DECIMAL(15,2) NOT NULL DEFAULT 0 CHECK (premium_total >= 0);
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS works_built_date       DATE;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS inspection_date        DATE;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS inspection_notes       TEXT;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS signoff_date           DATE;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS signoff_by             VARCHAR(255);
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS expected_release_date  DATE;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS bond_reminder_sent_for DATE;
ALTER TABLE public.escrows ADD COLUMN IF NOT EXISTS document_name          VARCHAR(255);

COMMENT ON COLUMN public.escrows.repair_estimate        IS 'Internal estimate of repairs to city standard. The repairs line = the higher of this and the defect list.';
COMMENT ON COLUMN public.escrows.premium_total          IS 'All bond / insurance premiums so far (first + renewals) = the premium line.';
COMMENT ON COLUMN public.escrows.bond_reminder_sent_for IS 'Bond expiry date the last renewal reminder was sent for.';

CREATE TABLE IF NOT EXISTS public.escrow_defects (
  id            UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  escrow_id     UUID          NOT NULL REFERENCES public.escrows(id) ON DELETE RESTRICT,
  description   TEXT          NOT NULL CHECK (btrim(description) <> ''),
  location      VARCHAR(255),
  repair_cost   DECIMAL(15,2) NOT NULL DEFAULT 0 CHECK (repair_cost >= 0),
  status        VARCHAR(10)   NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'repaired', 'waived')),
  repaired_at   DATE,
  recorded_by   UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_escrow_defects_escrow ON public.escrow_defects (escrow_id);
COMMENT ON TABLE public.escrow_defects IS 'Defect list from the inspection walk, with the repair cost of each item.';
DROP TRIGGER IF EXISTS trg_escrow_defects_updated_at ON public.escrow_defects;
CREATE TRIGGER trg_escrow_defects_updated_at BEFORE UPDATE ON public.escrow_defects
  FOR EACH ROW EXECUTE FUNCTION public.fn_set_updated_at();

CREATE TABLE IF NOT EXISTS public.escrow_events (
  id             UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  event_no       BIGINT        GENERATED ALWAYS AS IDENTITY UNIQUE,
  escrow_id      UUID          NOT NULL REFERENCES public.escrows(id) ON DELETE RESTRICT,
  project_id     UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  event_type     VARCHAR(30)   NOT NULL,
  status_after   VARCHAR(20)   NOT NULL,
  actor_user_id  UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  note           TEXT,
  created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_escrow_events_escrow ON public.escrow_events (escrow_id, event_no);
COMMENT ON TABLE public.escrow_events IS 'Append-only history of an escrow: created, each status, defects, renewals, cost changes.';

CREATE OR REPLACE FUNCTION public.fn_block_escrow_event_mutation()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  RAISE EXCEPTION 'Escrow history is append-only and cannot be changed.' USING ERRCODE = 'PT403';
END;
$$;
DROP TRIGGER IF EXISTS trg_escrow_events_immutable ON public.escrow_events;
CREATE TRIGGER trg_escrow_events_immutable BEFORE UPDATE OR DELETE ON public.escrow_events
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_escrow_event_mutation();

ALTER TABLE public.property_taxes ADD COLUMN IF NOT EXISTS jurisdiction_id    UUID REFERENCES public.jurisdictions(id) ON DELETE RESTRICT;
ALTER TABLE public.property_taxes ADD COLUMN IF NOT EXISTS assessed_value     DECIMAL(15,2) CHECK (assessed_value IS NULL OR assessed_value >= 0);
ALTER TABLE public.property_taxes ADD COLUMN IF NOT EXISTS tax_rate_percent   DECIMAL(7,4) CHECK (tax_rate_percent IS NULL OR tax_rate_percent BETWEEN 0 AND 100);
ALTER TABLE public.property_taxes ADD COLUMN IF NOT EXISTS reminded_days      INTEGER;
ALTER TABLE public.property_taxes ADD COLUMN IF NOT EXISTS paid_at            DATE;
COMMENT ON COLUMN public.property_taxes.reminded_days IS 'Days before the due date the last reminder went out (dedupe for the reminder job).';
COMMENT ON COLUMN public.property_taxes.status        IS 'estimated | billed | in_approval | sent_to_finance (paid) | cancelled.';

-- RLS for the new tables (same pattern as the other financial tables).
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['jurisdictions', 'escrow_defects', 'escrow_events'] LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon', t);
    EXECUTE format('REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.%I FROM authenticated', t);
    EXECUTE format('GRANT SELECT ON TABLE public.%I TO authenticated', t);
    EXECUTE format('GRANT ALL ON TABLE public.%I TO service_role', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', t || '_select_authenticated', t);
    EXECUTE format('CREATE POLICY %I ON public.%I FOR SELECT TO authenticated USING ((SELECT private.is_active_user()))',
                   t || '_select_authenticated', t);
  END LOOP;
END $$;


-- ============================================================================
-- SECTION B: LEDGER MOVEMENT TYPE
-- ============================================================================
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT conname FROM pg_constraint
            WHERE conrelid = 'public.contingency_ledger'::regclass AND contype = 'c'
              AND pg_get_constraintdef(oid) ILIKE '%movement_type%' LOOP
    EXECUTE format('ALTER TABLE public.contingency_ledger DROP CONSTRAINT %I', r.conname);
  END LOOP;
  ALTER TABLE public.contingency_ledger ADD CONSTRAINT chk_contingency_ledger_movement_type
    CHECK (movement_type IN ('initial_funding', 'bid_overrun', 'bid_savings', 'bid_reversal',
                             'variance_created', 'variance_adjusted', 'variance_cancelled',
                             'top_up', 'invoice_overage', 'long_tail'));
END $$;


-- ============================================================================
-- SECTION C: HELPERS
-- ============================================================================
CREATE OR REPLACE FUNCTION private.fin_can(p_user UUID, p_roles TEXT[])
RETURNS BOOLEAN LANGUAGE sql STABLE SET search_path = '' AS $$
  SELECT private.user_has_role(p_user, 'admin')
      OR EXISTS (SELECT 1 FROM unnest(p_roles) r WHERE private.user_has_role(p_user, r));
$$;

-- New long-tail line at the bottom of the budget, at $0.
CREATE OR REPLACE FUNCTION private.fin_new_long_tail_line(p_project UUID, p_subtype TEXT, p_name TEXT, p_actor UUID)
RETURNS UUID LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_id UUID;
BEGIN
  INSERT INTO public.budget_lines (project_id, line_type, line_subtype, name, section_name, sort_order,
                                   budget_amount, cash_bucket, created_by, updated_by)
  VALUES (p_project, 'long_tail', p_subtype, left(p_name, 255), 'Long-tail',
          COALESCE((SELECT max(sort_order) FROM public.budget_lines WHERE project_id = p_project AND deleted_at IS NULL), 0) + 10,
          0, 'land', p_actor, p_actor)
  RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

-- Set a long-tail line's amount, keeping the total flat: an increase comes
-- first from the template's placeholder line of the same kind (not linked to
-- any escrow / tax), then from contingency (baselined, ledger row); a decrease
-- goes back to contingency. Draft budgets: the Unallocated line absorbs it.
CREATE OR REPLACE FUNCTION private.fin_set_long_tail_amount(p_line_id UUID, p_amount NUMERIC, p_actor UUID, p_reason TEXT)
RETURNS VOID LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_line    public.budget_lines;
  v_status  TEXT;
  v_holder  public.budget_lines;
  v_delta   NUMERIC;
  v_take    NUMERIC := 0;
BEGIN
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id FOR UPDATE;
  v_delta := round(GREATEST(COALESCE(p_amount, 0), 0), 2) - v_line.budget_amount;
  IF v_delta = 0 THEN
    RETURN;
  END IF;
  SELECT budget_status INTO v_status FROM public.projects WHERE id = v_line.project_id;
  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  IF v_delta > 0 THEN
    SELECT * INTO v_holder FROM public.budget_lines b
     WHERE b.project_id = v_line.project_id AND b.line_type = 'long_tail' AND b.line_subtype = v_line.line_subtype
       AND b.id <> p_line_id AND b.deleted_at IS NULL AND b.budget_amount > 0
       AND NOT EXISTS (SELECT 1 FROM public.escrows e WHERE b.id IN (e.premium_line_id, e.repair_line_id))
       AND NOT EXISTS (SELECT 1 FROM public.property_taxes t WHERE t.budget_line_id = b.id)
     ORDER BY b.sort_order LIMIT 1 FOR UPDATE;
    IF FOUND THEN
      v_take := LEAST(v_delta, v_holder.budget_amount);
      UPDATE public.budget_lines SET budget_amount = budget_amount - v_take, updated_by = p_actor WHERE id = v_holder.id;
    END IF;
  END IF;

  UPDATE public.budget_lines SET budget_amount = budget_amount + v_delta, updated_by = p_actor WHERE id = p_line_id;
  IF v_status = 'baselined' AND v_delta - v_take <> 0 THEN
    PERFORM private.fin_move_contingency(v_line.project_id, -(v_delta - v_take), 'long_tail', p_actor,
                                         COALESCE(p_reason, v_line.name), p_line_id, NULL, NULL, NULL);
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION private.fin_escrow_event(p_escrow public.escrows, p_type TEXT, p_actor UUID, p_note TEXT)
RETURNS VOID LANGUAGE sql SET search_path = '' AS $$
  INSERT INTO public.escrow_events (escrow_id, project_id, event_type, status_after, actor_user_id, note)
  VALUES (p_escrow.id, p_escrow.project_id, p_type, p_escrow.status, p_actor, NULLIF(btrim(COALESCE(p_note, '')), ''));
$$;

-- Cash flow for the project's escrows and taxes (forecast rows, open months only).
CREATE OR REPLACE FUNCTION private.fin_refresh_long_tail_cash(p_project UUID)
RETURNS VOID LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
  DELETE FROM public.cash_flow_entries c
   WHERE c.project_id = p_project AND c.entry_kind = 'forecast'
     AND (c.escrow_id IS NOT NULL
          OR c.budget_line_id IN (SELECT budget_line_id FROM public.property_taxes WHERE project_id = p_project))
     AND NOT EXISTS (SELECT 1 FROM public.accounting_periods a WHERE a.period_month = c.period_month AND a.status = 'closed');

  INSERT INTO public.cash_flow_entries (project_id, budget_line_id, escrow_id, period_month, direction, cash_bucket,
                                        amount, entry_kind, source_note)
  SELECT p_project, x.line_id, x.escrow_id, date_trunc('month', x.d)::date, x.dir, 'land', x.amount, 'forecast', x.note
    FROM (
      -- posted cash goes out, and comes back in on release
      SELECT NULL::uuid AS line_id, e.id AS escrow_id, e.posted_date AS d, 'out' AS dir, e.secured_amount AS amount,
             'Escrow cash posted: ' || e.name AS note
        FROM public.escrows e
       WHERE e.project_id = p_project AND e.deleted_at IS NULL AND e.security_form = 'cash'
         AND e.status NOT IN ('planned', 'cancelled') AND e.posted_date IS NOT NULL
      UNION ALL
      SELECT NULL, e.id, COALESCE(e.released_date, e.expected_release_date), 'in', e.secured_amount,
             'Escrow cash returned: ' || e.name
        FROM public.escrows e
       WHERE e.project_id = p_project AND e.deleted_at IS NULL AND e.security_form = 'cash'
         AND e.status NOT IN ('planned', 'cancelled') AND e.posted_date IS NOT NULL
         AND COALESCE(e.released_date, e.expected_release_date) IS NOT NULL
      UNION ALL
      SELECT e.premium_line_id, e.id, COALESCE(e.posted_date, CURRENT_DATE), 'out', b.budget_amount,
             'Escrow premium: ' || e.name
        FROM public.escrows e JOIN public.budget_lines b ON b.id = e.premium_line_id
       WHERE e.project_id = p_project AND e.deleted_at IS NULL AND e.status <> 'cancelled' AND b.budget_amount > 0
      UNION ALL
      SELECT e.repair_line_id, e.id,
             COALESCE(e.signoff_date, e.inspection_date, e.expected_release_date, e.posted_date, CURRENT_DATE), 'out',
             b.budget_amount, 'Escrow repairs: ' || e.name
        FROM public.escrows e JOIN public.budget_lines b ON b.id = e.repair_line_id
       WHERE e.project_id = p_project AND e.deleted_at IS NULL AND e.status <> 'cancelled' AND b.budget_amount > 0
      UNION ALL
      SELECT t.budget_line_id, NULL, COALESCE(t.paid_at, t.due_date, make_date(t.tax_year, 12, 31)), 'out',
             COALESCE(t.actual_amount, round(t.estimated_amount * (100 - COALESCE(t.sold_portion_percent, 0)) / 100, 2)),
             format('Property tax %s %s #%s', t.tax_year, t.jurisdiction, t.installment_number)
        FROM public.property_taxes t
       WHERE t.project_id = p_project AND t.status <> 'cancelled' AND t.budget_line_id IS NOT NULL
    ) x
   WHERE x.amount > 0 AND x.d IS NOT NULL
     AND NOT EXISTS (SELECT 1 FROM public.accounting_periods a
                      WHERE a.period_month = date_trunc('month', x.d)::date AND a.status = 'closed');
END;
$$;

-- Escrow lines = premiums so far, and the higher of the repair estimate and the defect list.
CREATE OR REPLACE FUNCTION private.fin_sync_escrow(p_escrow_id UUID, p_actor UUID)
RETURNS VOID LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_e       public.escrows;
  v_defects NUMERIC;
BEGIN
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id;
  SELECT COALESCE(SUM(repair_cost), 0) INTO v_defects FROM public.escrow_defects
   WHERE escrow_id = p_escrow_id AND status <> 'waived';
  IF v_e.status = 'cancelled' THEN
    PERFORM private.fin_set_long_tail_amount(v_e.premium_line_id, 0, p_actor, 'Escrow cancelled: ' || v_e.name);
    PERFORM private.fin_set_long_tail_amount(v_e.repair_line_id, 0, p_actor, 'Escrow cancelled: ' || v_e.name);
  ELSE
    PERFORM private.fin_set_long_tail_amount(v_e.premium_line_id, v_e.premium_total, p_actor, 'Escrow premium: ' || v_e.name);
    PERFORM private.fin_set_long_tail_amount(v_e.repair_line_id, GREATEST(v_e.repair_estimate, v_defects), p_actor,
                                             'Escrow repairs: ' || v_e.name);
  END IF;
  PERFORM private.fin_refresh_long_tail_cash(v_e.project_id);
END;
$$;


-- ============================================================================
-- SECTION D: 7.1 / 7.2 ESCROWS
-- ============================================================================
-- p_data: name, beneficiary, covered_areas[], security_form, holder_type,
-- holder_name, secured_amount, premium_amount, premium_frequency, bond_number,
-- bond_expiry_date, jurisdiction_id, repair_estimate (NULL = jurisdiction %),
-- expected_release_date, notes.
CREATE OR REPLACE FUNCTION public.fn_save_escrow(p_project UUID, p_escrow_id UUID, p_actor UUID, p_data JSONB)
RETURNS SETOF public.escrows
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_project public.projects;
  v_e       public.escrows;
  v_old     public.escrows;
  v_pct     NUMERIC;
  v_repair  NUMERIC;
  v_secured NUMERIC := (p_data ->> 'secured_amount')::numeric;
  v_premium NUMERIC := COALESCE((p_data ->> 'premium_amount')::numeric, 0);
  v_areas   TEXT[]  := ARRAY(SELECT btrim(x) FROM jsonb_array_elements_text(COALESCE(p_data -> 'covered_areas', '[]'::jsonb)) x
                              WHERE btrim(x) <> '');
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['project_manager']) THEN
    RAISE EXCEPTION 'Only a project manager or admin can set up escrows.' USING ERRCODE = 'PT403';
  END IF;
  v_project := private.fin_lock_project(p_project, FALSE, FALSE);
  IF v_project.budget_status = 'none' THEN
    RAISE EXCEPTION 'Create the budget first: each escrow adds two budget lines.' USING ERRCODE = 'PT409';
  END IF;
  IF btrim(COALESCE(p_data ->> 'name', '')) = '' OR v_secured IS NULL OR v_secured < 0 THEN
    RAISE EXCEPTION 'An escrow needs a name and the value of the works it secures.' USING ERRCODE = 'PT422';
  END IF;
  IF array_length(v_areas, 1) IS NULL THEN
    RAISE EXCEPTION 'List at least one area the escrow covers (e.g. roads).' USING ERRCODE = 'PT422';
  END IF;
  IF p_data ->> 'security_form' = 'bond' AND btrim(COALESCE(p_data ->> 'holder_name', '')) = '' THEN
    RAISE EXCEPTION 'A bond needs its holder (insurance company, bank or other).' USING ERRCODE = 'PT422';
  END IF;
  IF v_premium < 0 THEN
    RAISE EXCEPTION 'The premium cannot be negative.' USING ERRCODE = 'PT422';
  END IF;

  v_repair := (p_data ->> 'repair_estimate')::numeric;
  IF v_repair IS NULL THEN
    SELECT repair_estimate_percent INTO v_pct FROM public.jurisdictions WHERE id = (p_data ->> 'jurisdiction_id')::uuid;
    v_repair := round(v_secured * COALESCE(v_pct, 0) / 100, 2);
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  IF p_escrow_id IS NULL THEN
    INSERT INTO public.escrows (
      project_id, name, beneficiary, covered_areas, security_form, holder_type, holder_name, secured_amount,
      premium_amount, premium_total, premium_frequency, bond_number, bond_expiry_date, jurisdiction_id,
      repair_estimate, expected_release_date, notes, status, created_by,
      premium_line_id, repair_line_id
    ) VALUES (
      p_project, btrim(p_data ->> 'name'), p_data ->> 'beneficiary', v_areas, p_data ->> 'security_form',
      NULLIF(p_data ->> 'holder_type', ''), NULLIF(btrim(COALESCE(p_data ->> 'holder_name', '')), ''), v_secured,
      v_premium, v_premium, COALESCE(p_data ->> 'premium_frequency', 'one_time'), NULLIF(p_data ->> 'bond_number', ''),
      (p_data ->> 'bond_expiry_date')::date, (p_data ->> 'jurisdiction_id')::uuid, v_repair,
      (p_data ->> 'expected_release_date')::date, NULLIF(p_data ->> 'notes', ''), 'planned', p_actor,
      private.fin_new_long_tail_line(p_project, 'escrow_bond_premium', 'Escrow premium: ' || btrim(p_data ->> 'name'), p_actor),
      private.fin_new_long_tail_line(p_project, 'escrow_repairs', 'Escrow repairs: ' || btrim(p_data ->> 'name'), p_actor)
    ) RETURNING * INTO v_e;
    PERFORM private.fin_escrow_event(v_e, 'created', p_actor, array_to_string(v_areas, ', '));
  ELSE
    SELECT * INTO v_old FROM public.escrows WHERE id = p_escrow_id AND project_id = p_project AND deleted_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Escrow not found' USING ERRCODE = 'PT404';
    END IF;
    IF v_old.status IN ('released', 'cancelled') THEN
      RAISE EXCEPTION 'This escrow is % and can no longer be changed.', v_old.status USING ERRCODE = 'PT409';
    END IF;
    UPDATE public.escrows SET
      name = btrim(p_data ->> 'name'), beneficiary = p_data ->> 'beneficiary', covered_areas = v_areas,
      security_form = p_data ->> 'security_form', holder_type = NULLIF(p_data ->> 'holder_type', ''),
      holder_name = NULLIF(btrim(COALESCE(p_data ->> 'holder_name', '')), ''), secured_amount = v_secured,
      premium_total = premium_total - premium_amount + v_premium, premium_amount = v_premium,
      premium_frequency = COALESCE(p_data ->> 'premium_frequency', premium_frequency),
      bond_number = NULLIF(p_data ->> 'bond_number', ''), bond_expiry_date = (p_data ->> 'bond_expiry_date')::date,
      jurisdiction_id = (p_data ->> 'jurisdiction_id')::uuid, repair_estimate = v_repair,
      expected_release_date = (p_data ->> 'expected_release_date')::date, notes = NULLIF(p_data ->> 'notes', ''),
      bond_reminder_sent_for = CASE WHEN (p_data ->> 'bond_expiry_date')::date IS DISTINCT FROM bond_expiry_date
                                    THEN NULL ELSE bond_reminder_sent_for END
     WHERE id = p_escrow_id RETURNING * INTO v_e;
    UPDATE public.budget_lines SET name = left('Escrow premium: ' || v_e.name, 255) WHERE id = v_e.premium_line_id;
    UPDATE public.budget_lines SET name = left('Escrow repairs: ' || v_e.name, 255) WHERE id = v_e.repair_line_id;
    PERFORM private.fin_escrow_event(v_e, 'updated', p_actor, NULL);
  END IF;

  PERFORM private.fin_sync_escrow(v_e.id, p_actor);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN QUERY SELECT * FROM public.escrows WHERE id = v_e.id;
END;
$$;

COMMENT ON FUNCTION public.fn_save_escrow(UUID, UUID, UUID, JSONB) IS
  'Creates (p_escrow_id NULL) or edits an escrow. A new escrow gets its two cost lines at the bottom of the budget: premium and repairs to city standard (estimate, or the jurisdiction % of the secured value).';

-- 7.3 lifecycle. One step forward at a time; corrections only with open defects.
CREATE OR REPLACE FUNCTION public.fn_escrow_transition(
  p_escrow_id UUID, p_actor UUID, p_to TEXT, p_date DATE, p_note TEXT, p_signoff_by TEXT
)
RETURNS SETOF public.escrows
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_e     public.escrows;
  v_open  INT;
  v_ok    BOOLEAN;
  v_date  DATE := COALESCE(p_date, CURRENT_DATE);
BEGIN
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id AND deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Escrow not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_e.project_id, FALSE, FALSE);
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id FOR UPDATE;

  IF p_to IN ('posted', 'released', 'cancelled') THEN
    IF NOT private.fin_can(p_actor, ARRAY['project_manager']) THEN
      RAISE EXCEPTION 'Only a project manager or admin can post, release or cancel an escrow.' USING ERRCODE = 'PT403';
    END IF;
  ELSIF NOT private.fin_can(p_actor, ARRAY['field_manager', 'project_manager']) THEN
    RAISE EXCEPTION 'Only a field manager, project manager or admin can record the escrow works.' USING ERRCODE = 'PT403';
  END IF;

  SELECT count(*) INTO v_open FROM public.escrow_defects WHERE escrow_id = p_escrow_id AND status = 'open';
  v_ok := CASE p_to
    WHEN 'posted'      THEN v_e.status = 'planned'
    WHEN 'works_built' THEN v_e.status = 'posted'
    WHEN 'inspection'  THEN v_e.status IN ('works_built', 'corrections')
    WHEN 'corrections' THEN v_e.status = 'inspection' AND v_open > 0
    WHEN 'signed_off'  THEN v_e.status IN ('inspection', 'corrections')
    WHEN 'released'    THEN v_e.status = 'signed_off'
    WHEN 'cancelled'   THEN v_e.status IN ('planned', 'posted')
    ELSE FALSE END;
  IF NOT v_ok THEN
    RAISE EXCEPTION 'An escrow that is % cannot move to %.', replace(v_e.status, '_', ' '), replace(p_to, '_', ' ')
      USING ERRCODE = 'PT409';
  END IF;
  IF p_to = 'signed_off' AND v_open > 0 THEN
    RAISE EXCEPTION 'Repair or waive the % open defect(s) before the government sign-off.', v_open USING ERRCODE = 'PT409';
  END IF;
  IF p_to = 'signed_off' AND btrim(COALESCE(p_signoff_by, '')) = '' THEN
    RAISE EXCEPTION 'Record who signed off for the government.' USING ERRCODE = 'PT422';
  END IF;
  IF p_to = 'posted' AND v_e.security_form = 'bond' AND v_e.bond_expiry_date IS NULL THEN
    RAISE EXCEPTION 'Enter the bond expiry date before posting.' USING ERRCODE = 'PT422';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.escrows SET
    status           = p_to,
    posted_date      = CASE WHEN p_to = 'posted' THEN v_date ELSE posted_date END,
    works_built_date = CASE WHEN p_to = 'works_built' THEN v_date ELSE works_built_date END,
    inspection_date  = CASE WHEN p_to = 'inspection' THEN v_date ELSE inspection_date END,
    inspection_notes = CASE WHEN p_to = 'inspection' THEN NULLIF(btrim(COALESCE(p_note, '')), '') ELSE inspection_notes END,
    signoff_date     = CASE WHEN p_to = 'signed_off' THEN v_date ELSE signoff_date END,
    signoff_by       = CASE WHEN p_to = 'signed_off' THEN btrim(p_signoff_by) ELSE signoff_by END,
    released_date    = CASE WHEN p_to = 'released' THEN GREATEST(v_date, COALESCE(posted_date, v_date)) ELSE released_date END
   WHERE id = p_escrow_id RETURNING * INTO v_e;
  PERFORM private.fin_escrow_event(v_e, p_to, p_actor, COALESCE(p_note, p_signoff_by));
  PERFORM private.fin_sync_escrow(p_escrow_id, p_actor);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_e;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_save_escrow_defect(
  p_escrow_id UUID, p_defect_id UUID, p_actor UUID, p_description TEXT, p_location TEXT, p_cost NUMERIC, p_status TEXT
)
RETURNS SETOF public.escrow_defects
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_e  public.escrows;
  v_d  public.escrow_defects;
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['field_manager', 'project_manager']) THEN
    RAISE EXCEPTION 'Only a field manager, project manager or admin can record defects.' USING ERRCODE = 'PT403';
  END IF;
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id AND deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Escrow not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_e.project_id, FALSE, FALSE);
  IF v_e.status NOT IN ('inspection', 'corrections') THEN
    RAISE EXCEPTION 'Defects are recorded at the inspection walk and during corrections.' USING ERRCODE = 'PT409';
  END IF;
  IF btrim(COALESCE(p_description, '')) = '' OR COALESCE(p_cost, 0) < 0 THEN
    RAISE EXCEPTION 'A defect needs a description and a repair cost of $0 or more.' USING ERRCODE = 'PT422';
  END IF;

  IF p_defect_id IS NULL THEN
    INSERT INTO public.escrow_defects (escrow_id, description, location, repair_cost, status, recorded_by)
    VALUES (p_escrow_id, btrim(p_description), NULLIF(btrim(COALESCE(p_location, '')), ''), COALESCE(p_cost, 0),
            COALESCE(p_status, 'open'), p_actor)
    RETURNING * INTO v_d;
  ELSE
    UPDATE public.escrow_defects
       SET description = btrim(p_description), location = NULLIF(btrim(COALESCE(p_location, '')), ''),
           repair_cost = COALESCE(p_cost, 0), status = COALESCE(p_status, status),
           repaired_at = CASE WHEN p_status = 'repaired' THEN COALESCE(repaired_at, CURRENT_DATE)
                              WHEN p_status = 'open' THEN NULL ELSE repaired_at END
     WHERE id = p_defect_id AND escrow_id = p_escrow_id RETURNING * INTO v_d;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'Defect not found' USING ERRCODE = 'PT404';
    END IF;
  END IF;
  PERFORM private.fin_escrow_event(v_e, 'defect_' || v_d.status, p_actor, format('%s (%s)', v_d.description, v_d.repair_cost));
  PERFORM private.fin_sync_escrow(p_escrow_id, p_actor);
  RETURN NEXT v_d;
END;
$$;

-- Yearly bond renewal: the new premium is added to the premium line.
CREATE OR REPLACE FUNCTION public.fn_renew_escrow_bond(p_escrow_id UUID, p_actor UUID, p_new_expiry DATE, p_premium NUMERIC)
RETURNS SETOF public.escrows
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_e public.escrows;
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['project_manager', 'finance']) THEN
    RAISE EXCEPTION 'Only a project manager, finance or admin can record a bond renewal.' USING ERRCODE = 'PT403';
  END IF;
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id AND deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Escrow not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_e.project_id, FALSE, FALSE);
  SELECT * INTO v_e FROM public.escrows WHERE id = p_escrow_id FOR UPDATE;
  IF v_e.security_form <> 'bond' OR v_e.status IN ('released', 'cancelled') THEN
    RAISE EXCEPTION 'Only an open bond can be renewed.' USING ERRCODE = 'PT409';
  END IF;
  IF p_new_expiry IS NULL OR p_new_expiry <= COALESCE(v_e.bond_expiry_date, CURRENT_DATE) OR COALESCE(p_premium, -1) < 0 THEN
    RAISE EXCEPTION 'Enter a new expiry date after the current one and the renewal premium.' USING ERRCODE = 'PT422';
  END IF;
  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.escrows SET bond_expiry_date = p_new_expiry, premium_total = premium_total + p_premium,
                            bond_reminder_sent_for = NULL
   WHERE id = p_escrow_id RETURNING * INTO v_e;
  PERFORM private.fin_escrow_event(v_e, 'bond_renewed', p_actor, format('Until %s, premium %s', p_new_expiry, p_premium));
  PERFORM private.fin_sync_escrow(p_escrow_id, p_actor);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_e;
END;
$$;


-- ============================================================================
-- SECTION E: 7.4 PROPERTY TAXES
-- ============================================================================
CREATE OR REPLACE FUNCTION private.fin_sync_tax_line(p_line_id UUID, p_actor UUID)
RETURNS VOID LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_total NUMERIC;
BEGIN
  SELECT COALESCE(SUM(COALESCE(actual_amount, round(estimated_amount * (100 - COALESCE(sold_portion_percent, 0)) / 100, 2))), 0)
    INTO v_total FROM public.property_taxes WHERE budget_line_id = p_line_id AND status <> 'cancelled';
  PERFORM private.fin_set_long_tail_amount(p_line_id, v_total, p_actor, 'Property tax');
END;
$$;

-- One year for one jurisdiction: instalments on its due dates, estimate by
-- basis (prior_year_actual | assessed_value | manual), split evenly.
CREATE OR REPLACE FUNCTION public.fn_set_property_tax_year(
  p_project UUID, p_actor UUID, p_year INT, p_jurisdiction_id UUID, p_basis TEXT,
  p_amount NUMERIC, p_assessed NUMERIC, p_rate NUMERIC, p_sold_percent NUMERIC, p_parcel TEXT
)
RETURNS JSONB
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_project public.projects;
  v_j       public.jurisdictions;
  v_line    UUID;
  v_total   NUMERIC;
  v_n       INT;
  v_i       INT := 0;
  v_inst    JSONB;
  v_each    NUMERIC;
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['project_manager', 'finance']) THEN
    RAISE EXCEPTION 'Only a project manager, finance or admin can set property taxes.' USING ERRCODE = 'PT403';
  END IF;
  v_project := private.fin_lock_project(p_project, FALSE, FALSE);
  IF v_project.budget_status = 'none' THEN
    RAISE EXCEPTION 'Create the budget first: each tax year is a budget line.' USING ERRCODE = 'PT409';
  END IF;
  SELECT * INTO v_j FROM public.jurisdictions WHERE id = p_jurisdiction_id AND deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Choose the city or county the tax is paid to.' USING ERRCODE = 'PT422';
  END IF;
  IF p_year IS NULL OR p_year < 2000 OR p_year > 2200 THEN
    RAISE EXCEPTION 'Enter a valid tax year.' USING ERRCODE = 'PT422';
  END IF;
  IF COALESCE(p_sold_percent, 0) NOT BETWEEN 0 AND 100 THEN
    RAISE EXCEPTION 'The sold portion is a %% between 0 and 100.' USING ERRCODE = 'PT422';
  END IF;

  v_total := CASE p_basis
    -- Last year's bills; an instalment not billed yet counts at its estimate.
    WHEN 'prior_year_actual' THEN (SELECT SUM(COALESCE(actual_amount, estimated_amount)) FROM public.property_taxes
                                    WHERE project_id = p_project AND jurisdiction_id = p_jurisdiction_id
                                      AND tax_year = p_year - 1 AND status <> 'cancelled'
                                   HAVING count(actual_amount) > 0)
    WHEN 'assessed_value' THEN round(p_assessed * p_rate / 100, 2)
    WHEN 'manual' THEN p_amount
  END;
  IF v_total IS NULL OR v_total < 0 THEN
    RAISE EXCEPTION '%', CASE p_basis
      WHEN 'prior_year_actual' THEN format('There is no actual for %s to start from. Enter the amount or the assessed value.', p_year - 1)
      WHEN 'assessed_value' THEN 'Enter the assessed value and the tax rate %.'
      ELSE 'Enter the estimated amount.' END USING ERRCODE = 'PT422';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  SELECT budget_line_id INTO v_line FROM public.property_taxes
   WHERE project_id = p_project AND tax_year = p_year AND budget_line_id IS NOT NULL LIMIT 1;
  IF v_line IS NULL THEN
    v_line := private.fin_new_long_tail_line(p_project, 'property_tax', format('Property tax %s', p_year), p_actor);
  END IF;

  v_n := jsonb_array_length(v_j.tax_installments);
  v_each := round(v_total / v_n, 2);
  FOR v_inst IN SELECT value FROM jsonb_array_elements(v_j.tax_installments) LOOP
    v_i := v_i + 1;
    INSERT INTO public.property_taxes (
      project_id, budget_line_id, tax_year, jurisdiction, jurisdiction_id, parcel_reference, installment_number,
      due_date, estimate_basis, estimated_amount, assessed_value, tax_rate_percent, sold_portion_percent, status, created_by
    ) VALUES (
      p_project, v_line, p_year, v_j.name, v_j.id, NULLIF(btrim(COALESCE(p_parcel, '')), ''), v_i,
      -- Day past the month's end (e.g. 31 in June) becomes the last day.
      LEAST(make_date(p_year, (v_inst ->> 'month')::int, 1) + ((v_inst ->> 'day')::int - 1),
            (make_date(p_year, (v_inst ->> 'month')::int, 1) + INTERVAL '1 month - 1 day')::date),
      p_basis, CASE WHEN v_i = v_n THEN v_total - v_each * (v_n - 1) ELSE v_each END,
      p_assessed, p_rate, p_sold_percent, 'estimated', p_actor
    )
    ON CONFLICT (project_id, tax_year, jurisdiction, installment_number) DO UPDATE
       SET estimate_basis = EXCLUDED.estimate_basis, estimated_amount = EXCLUDED.estimated_amount,
           assessed_value = EXCLUDED.assessed_value, tax_rate_percent = EXCLUDED.tax_rate_percent,
           sold_portion_percent = EXCLUDED.sold_portion_percent, due_date = EXCLUDED.due_date,
           parcel_reference = COALESCE(EXCLUDED.parcel_reference, public.property_taxes.parcel_reference),
           jurisdiction_id = EXCLUDED.jurisdiction_id
     WHERE public.property_taxes.status IN ('estimated', 'billed');
  END LOOP;

  PERFORM private.fin_sync_tax_line(v_line, p_actor);
  PERFORM private.fin_refresh_long_tail_cash(p_project);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN jsonb_build_object('budget_line_id', v_line, 'estimated_total', v_total, 'installments', v_n);
END;
$$;

-- Edit one instalment: billed / actual amount (catches increases), due date, paid, cancelled.
CREATE OR REPLACE FUNCTION public.fn_update_property_tax(
  p_id UUID, p_actor UUID, p_estimated NUMERIC, p_actual NUMERIC, p_due DATE, p_status TEXT, p_sold_percent NUMERIC
)
RETURNS SETOF public.property_taxes
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE v_t public.property_taxes;
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['project_manager', 'finance']) THEN
    RAISE EXCEPTION 'Only a project manager, finance or admin can change property taxes.' USING ERRCODE = 'PT403';
  END IF;
  SELECT * INTO v_t FROM public.property_taxes WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Property tax not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_t.project_id, FALSE, FALSE);
  IF p_status IS NOT NULL AND p_status NOT IN ('estimated', 'billed', 'sent_to_finance', 'cancelled') THEN
    RAISE EXCEPTION 'Unknown property tax status' USING ERRCODE = 'PT422';
  END IF;
  IF COALESCE(p_estimated, 0) < 0 OR COALESCE(p_actual, 0) < 0 OR COALESCE(p_sold_percent, 0) NOT BETWEEN 0 AND 100 THEN
    RAISE EXCEPTION 'Amounts must be $0 or more and the sold portion 0 to 100%%.' USING ERRCODE = 'PT422';
  END IF;
  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.property_taxes SET
    estimated_amount = COALESCE(p_estimated, estimated_amount),
    actual_amount = p_actual,
    due_date = COALESCE(p_due, due_date),
    sold_portion_percent = COALESCE(p_sold_percent, sold_portion_percent),
    status = COALESCE(p_status, CASE WHEN p_actual IS NOT NULL AND status = 'estimated' THEN 'billed' ELSE status END),
    paid_at = CASE WHEN COALESCE(p_status, status) = 'sent_to_finance' THEN COALESCE(paid_at, CURRENT_DATE) ELSE NULL END,
    reminded_days = CASE WHEN p_due IS DISTINCT FROM NULL AND p_due <> due_date THEN NULL ELSE reminded_days END
   WHERE id = p_id RETURNING * INTO v_t;
  PERFORM private.fin_sync_tax_line(v_t.budget_line_id, p_actor);
  PERFORM private.fin_refresh_long_tail_cash(v_t.project_id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_t;
END;
$$;

-- As lots / homes sell: the sold % on every open instalment from a year on.
CREATE OR REPLACE FUNCTION public.fn_set_tax_sold_portion(p_project UUID, p_actor UUID, p_percent NUMERIC, p_from_year INT)
RETURNS INT
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE
  v_line UUID;
  v_n    INT;
BEGIN
  IF NOT private.fin_can(p_actor, ARRAY['project_manager', 'finance']) THEN
    RAISE EXCEPTION 'Only a project manager, finance or admin can change property taxes.' USING ERRCODE = 'PT403';
  END IF;
  IF p_percent IS NULL OR p_percent NOT BETWEEN 0 AND 100 THEN
    RAISE EXCEPTION 'The sold portion is a %% between 0 and 100.' USING ERRCODE = 'PT422';
  END IF;
  PERFORM private.fin_lock_project(p_project, FALSE, FALSE);
  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.property_taxes SET sold_portion_percent = p_percent
   WHERE project_id = p_project AND tax_year >= COALESCE(p_from_year, 0) AND status IN ('estimated', 'billed')
     AND actual_amount IS NULL;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  FOR v_line IN SELECT DISTINCT budget_line_id FROM public.property_taxes
                 WHERE project_id = p_project AND budget_line_id IS NOT NULL LOOP
    PERFORM private.fin_sync_tax_line(v_line, p_actor);
  END LOOP;
  PERFORM private.fin_refresh_long_tail_cash(p_project);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN v_n;
END;
$$;


-- ============================================================================
-- SECTION F: 5.1 HEALTH INPUTS — long-tail paid counts as spent
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_project_health_inputs(p_project_id UUID)
RETURNS JSONB
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  SELECT jsonb_build_object(
    'project_id',            p.id,
    'project_name',          p.name,
    'status',                p.status,
    'budget_status',         p.budget_status,
    'archived',              p.archived_at IS NOT NULL,
    'manager_id',            p.manager_id,
    'field_manager_id',      p.field_manager_id,
    'groundbreaking_at',     p.groundbreaking_at,
    'reserve',               p.long_tail_reserve_amount,
    'contingency',           (SELECT b.budget_amount FROM public.budget_lines b
                               WHERE b.project_id = p.id AND b.line_type = 'contingency' AND b.deleted_at IS NULL),
    'contingency_base',      COALESCE(p.contingency_at_groundbreaking,
                               (SELECT cb.approved_amount FROM public.contingency_buckets cb
                                 WHERE cb.project_id = p.id AND cb.bucket_kind = 'initial')),
    'total_budget',          (SELECT COALESCE(SUM(b.budget_amount), 0) FROM public.budget_lines b
                               WHERE b.project_id = p.id AND b.deleted_at IS NULL),
    'lines',                 (SELECT COALESCE(jsonb_agg(jsonb_build_object(
                                'committed',   b.committed_amount,
                                'approved',    COALESCE(pay.approved, 0),
                                'sent',        COALESCE(pay.sent, 0),
                                'land_closed', COALESCE(lc.closed, 0) + COALESCE(lt.paid, 0))), '[]'::jsonb)
                               FROM public.budget_lines b
                               LEFT JOIN LATERAL (
                                 SELECT SUM(x.amount) FILTER (WHERE x.status = 'approved')        AS approved,
                                        SUM(x.amount) FILTER (WHERE x.status = 'sent_to_finance') AS sent
                                   FROM public.payment_approvals x WHERE x.budget_line_id = b.id
                               ) pay ON TRUE
                               LEFT JOIN LATERAL (
                                 SELECT SUM(y.amount) AS closed FROM public.land_closings y
                                  WHERE y.budget_line_id = b.id AND y.status = 'closed'
                               ) lc ON TRUE
                               -- Long-tail: taxes paid, and an escrow's costs once it is released.
                               LEFT JOIN LATERAL (
                                 SELECT COALESCE((SELECT SUM(t.actual_amount) FROM public.property_taxes t
                                                   WHERE t.budget_line_id = b.id AND t.status = 'sent_to_finance'), 0)
                                      + COALESCE((SELECT b.budget_amount FROM public.escrows e
                                                   WHERE b.id IN (e.premium_line_id, e.repair_line_id)
                                                     AND e.status = 'released' LIMIT 1), 0) AS paid
                               ) lt ON b.line_type = 'long_tail'
                              WHERE b.project_id = p.id AND b.deleted_at IS NULL AND b.line_type <> 'contingency'),
    'milestones_total',      ms.total,
    'milestones_completed',  ms.done,
    'near_zero_percent',     COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                                        WHERE setting_key = 'contingency_near_zero_percent'), 5)
  )
  FROM public.projects p
  CROSS JOIN LATERAL (
    SELECT count(*) AS total, count(*) FILTER (WHERE m.status = 'completed') AS done
      FROM public.milestones m
      JOIN public.tasks t ON t.id = m.task_id
     WHERE t.project_id = p.id AND t.deleted_at IS NULL AND m.status <> 'cancelled'
  ) ms
  WHERE p.id = p_project_id AND p.deleted_at IS NULL;
$$;


-- ============================================================================
-- SECTION G: 7.5 READ SURFACE
-- ============================================================================
CREATE OR REPLACE VIEW public.v_escrows
WITH (security_invoker = true) AS
SELECT e.id, e.project_id, p.name AS project_name, e.name, e.beneficiary, e.covered_areas, e.security_form,
       e.holder_type, e.holder_name, e.secured_amount, e.premium_amount, e.premium_total, e.premium_frequency,
       e.bond_number, e.bond_expiry_date, e.status, e.posted_date, e.works_built_date, e.inspection_date,
       e.inspection_notes, e.signoff_date, e.signoff_by, e.expected_release_date, e.released_date,
       e.jurisdiction_id, j.name AS jurisdiction_name, e.repair_estimate,
       e.premium_line_id, pl.budget_amount AS premium_line_amount,
       e.repair_line_id, rl.budget_amount AS repair_line_amount,
       COALESCE(d.open_count, 0) AS open_defects, COALESCE(d.total, 0) AS defects_total,
       e.document_path, e.document_name, e.notes, e.created_at, e.updated_at
  FROM public.escrows e
  JOIN public.projects p ON p.id = e.project_id AND p.deleted_at IS NULL
  LEFT JOIN public.jurisdictions j ON j.id = e.jurisdiction_id
  LEFT JOIN public.budget_lines pl ON pl.id = e.premium_line_id
  LEFT JOIN public.budget_lines rl ON rl.id = e.repair_line_id
  LEFT JOIN LATERAL (
    SELECT count(*) FILTER (WHERE status = 'open') AS open_count,
           SUM(repair_cost) FILTER (WHERE status <> 'waived') AS total
      FROM public.escrow_defects WHERE escrow_id = e.id
  ) d ON TRUE
 WHERE e.deleted_at IS NULL;

CREATE OR REPLACE VIEW public.v_property_taxes
WITH (security_invoker = true) AS
SELECT t.id, t.project_id, p.name AS project_name, t.budget_line_id, t.tax_year, t.jurisdiction, t.jurisdiction_id,
       t.parcel_reference, t.installment_number, t.due_date, t.estimate_basis, t.estimated_amount, t.actual_amount,
       t.assessed_value, t.tax_rate_percent, t.sold_portion_percent,
       COALESCE(t.actual_amount, round(t.estimated_amount * (100 - COALESCE(t.sold_portion_percent, 0)) / 100, 2)) AS amount_due,
       t.actual_amount - t.estimated_amount AS increase, t.status, t.paid_at, t.reminded_days,
       p.manager_id, t.created_at, t.updated_at
  FROM public.property_taxes t
  JOIN public.projects p ON p.id = t.project_id AND p.deleted_at IS NULL;

COMMENT ON VIEW public.v_property_taxes IS
  'Property tax instalments with the amount due (actual, else estimate less the sold portion) and the increase of actual over estimate.';


-- ============================================================================
-- SECTION H: PRIVILEGES
-- ============================================================================
REVOKE ALL ON public.v_escrows, public.v_property_taxes FROM PUBLIC, anon;
GRANT SELECT ON public.v_escrows, public.v_property_taxes TO authenticated, service_role;

REVOKE ALL ON FUNCTION private.fin_can(uuid, text[])                                      FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.fin_can(uuid, text[])                                   TO authenticated, service_role;
REVOKE ALL ON FUNCTION private.fin_new_long_tail_line(uuid, text, text, uuid)             FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_set_long_tail_amount(uuid, numeric, uuid, text)        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_escrow_event(public.escrows, text, uuid, text)         FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_refresh_long_tail_cash(uuid)                           FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_sync_escrow(uuid, uuid)                                FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_sync_tax_line(uuid, uuid)                              FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.fin_new_long_tail_line(uuid, text, text, uuid)          TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_set_long_tail_amount(uuid, numeric, uuid, text)     TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_escrow_event(public.escrows, text, uuid, text)      TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_refresh_long_tail_cash(uuid)                        TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_sync_escrow(uuid, uuid)                             TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_sync_tax_line(uuid, uuid)                           TO service_role;

REVOKE ALL ON FUNCTION public.fn_block_escrow_event_mutation() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_save_escrow(uuid, uuid, uuid, jsonb)                                         FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_escrow_transition(uuid, uuid, text, date, text, text)                        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_save_escrow_defect(uuid, uuid, uuid, text, text, numeric, text)              FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_renew_escrow_bond(uuid, uuid, date, numeric)                                 FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_set_property_tax_year(uuid, uuid, int, uuid, text, numeric, numeric, numeric, numeric, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_update_property_tax(uuid, uuid, numeric, numeric, date, text, numeric)       FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_set_tax_sold_portion(uuid, uuid, numeric, int)                               FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_save_escrow(uuid, uuid, uuid, jsonb)                                      TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_escrow_transition(uuid, uuid, text, date, text, text)                     TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_save_escrow_defect(uuid, uuid, uuid, text, text, numeric, text)           TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_renew_escrow_bond(uuid, uuid, date, numeric)                              TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_set_property_tax_year(uuid, uuid, int, uuid, text, numeric, numeric, numeric, numeric, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_update_property_tax(uuid, uuid, numeric, numeric, date, text, numeric)    TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_set_tax_sold_portion(uuid, uuid, numeric, int)                            TO service_role;


-- ============================================================================
-- SECTION I: SETTINGS AND VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description) VALUES
  ('bond_renewal_reminder_days', '60'::jsonb, 'Days before a bond expires that the renewal reminder is sent (again at 14 days).')
ON CONFLICT (setting_key) DO NOTHING;

INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.8.0 (20261128_financial_phase7_long_tail)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;

COMMIT;
