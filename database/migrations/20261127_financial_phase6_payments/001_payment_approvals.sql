-- ============================================================================
-- BluOnX Financial Automation — Phase 6 · Module 6
-- 001  PAYMENT APPROVAL WORKFLOW & FINANCE HAND-OFF (schema change script)
-- ============================================================================
-- Version:  4.7.0
-- Date:     November 27, 2026
-- Requires: Phases 1-5 (last: 20261126_financial_phase5_health)
-- Engine:   PostgreSQL 15+ (Supabase)
-- ============================================================================
--
-- WHAT THIS SCRIPT DOES
--   6.1 fn_request_payment: full, progress (% of the line) or retainage
--       release, with the contract's retainage held back.
--   6.2 / 6.3 fn_payment_approval_step records each approval the Python rules
--       engine (app/services/payment_rules.py) decides, and re-checks the rules
--       that must never break: internal employees only, two different people
--       above the limit or after an external confirmation, an executive above
--       the executive threshold. fn_reject_payment / fn_resubmit_payment /
--       fn_cancel_payment. payment_approval_events = append-only history.
--   6.4 Final approval creates the finance_handoffs row with its PO number and
--       payload, and the expected cash-flow entry (6.5), in the same transaction.
--   6.6 fn_mark_finance_handoff: sent to finance (email_log proves delivery).
--
-- SAFETY: additive / CREATE OR REPLACE, idempotent, one transaction.
-- Rows written: settings (never overwritten) and the schema_version marker.
-- ============================================================================

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $$
BEGIN
  IF to_regprocedure('public.fn_sync_financial_alerts(uuid, jsonb)') IS NULL THEN
    RAISE EXCEPTION 'Phases 1 to 5 must be applied first.';
  END IF;
END $$;

-- ============================================================================
-- SECTION A: COLUMNS
-- ============================================================================
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS gross_amount          DECIMAL(15,2);
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS work_confirmed_by     UUID REFERENCES public.users(id) ON DELETE RESTRICT;
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS work_confirmed_at     TIMESTAMPTZ;
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS confirmed_by_external BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS executive_required    BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS resubmitted_from      UUID REFERENCES public.payment_approvals(id) ON DELETE RESTRICT;
ALTER TABLE public.payment_approvals ADD COLUMN IF NOT EXISTS approved_at           TIMESTAMPTZ;

COMMENT ON COLUMN public.payment_approvals.amount                IS 'Net amount to pay = gross_amount − retainage_amount (a retainage release pays the retainage held).';
COMMENT ON COLUMN public.payment_approvals.gross_amount          IS 'Value of the work being paid (full: what is left on the line; progress: % of the line). NULL on Phase 2 invoice requests = amount.';
COMMENT ON COLUMN public.payment_approvals.work_confirmed_by     IS 'Field manager who confirmed the work is complete (may be external).';
COMMENT ON COLUMN public.payment_approvals.confirmed_by_external IS 'TRUE when the work was confirmed by an external / temporary field manager: a second, internal approval is always needed.';
COMMENT ON COLUMN public.payment_approvals.executive_required    IS 'Above financial_settings.executive_approval_threshold: an executive approval is also needed.';

ALTER TABLE public.finance_handoffs ADD COLUMN IF NOT EXISTS handoff_error TEXT;
COMMENT ON COLUMN public.finance_handoffs.handoff_error IS 'Why the last hand-off email failed. The daily summary job retries failed hand-offs.';


-- ============================================================================
-- SECTION B: HISTORY (append-only)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.payment_approval_events (
  id                   UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  event_no             BIGINT        GENERATED ALWAYS AS IDENTITY UNIQUE,
  payment_approval_id  UUID          NOT NULL REFERENCES public.payment_approvals(id) ON DELETE RESTRICT,
  project_id           UUID          NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
  event_type           VARCHAR(30)   NOT NULL
                                     CHECK (event_type IN ('requested', 'work_confirmed', 'field_approved', 'routed_to_manager',
                                                           'manager_approved', 'routed_to_executive', 'executive_approved',
                                                           'approved', 'rejected', 'resubmitted', 'cancelled',
                                                           'sent_to_finance', 'handoff_failed')),
  status_after         VARCHAR(20)   NOT NULL,
  actor_user_id        UUID          REFERENCES public.users(id) ON DELETE RESTRICT,
  routed_to_user_id    UUID          REFERENCES public.users(id) ON DELETE SET NULL,
  note                 TEXT,
  created_at           TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payment_approval_events_pa ON public.payment_approval_events (payment_approval_id, event_no);

COMMENT ON TABLE public.payment_approval_events IS
  'Append-only audit trail of every payment approval: request, work confirmation, each approval, routing, rejection, hand-off to finance.';

CREATE OR REPLACE FUNCTION public.fn_block_payment_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  RAISE EXCEPTION 'Payment approval history is append-only and cannot be changed.' USING ERRCODE = 'PT403';
END;
$$;

DROP TRIGGER IF EXISTS trg_payment_approval_events_immutable ON public.payment_approval_events;
CREATE TRIGGER trg_payment_approval_events_immutable
  BEFORE UPDATE OR DELETE ON public.payment_approval_events
  FOR EACH ROW EXECUTE FUNCTION public.fn_block_payment_event_mutation();
DROP TRIGGER IF EXISTS trg_payment_approval_events_no_truncate ON public.payment_approval_events;
CREATE TRIGGER trg_payment_approval_events_no_truncate
  BEFORE TRUNCATE ON public.payment_approval_events
  FOR EACH STATEMENT EXECUTE FUNCTION public.fn_block_payment_event_mutation();

ALTER TABLE public.payment_approval_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.payment_approval_events FROM anon, authenticated;
GRANT SELECT ON TABLE public.payment_approval_events TO authenticated;
GRANT ALL ON TABLE public.payment_approval_events TO service_role;
DROP POLICY IF EXISTS payment_approval_events_select_authenticated ON public.payment_approval_events;
CREATE POLICY payment_approval_events_select_authenticated
  ON public.payment_approval_events FOR SELECT TO authenticated
  USING ((SELECT private.is_active_user()));


-- ============================================================================
-- SECTION C: HELPERS
-- ============================================================================
-- Amount a user may approve alone. NULL = no limit (a manager without a
-- personal limit). A field manager without one gets the default.
CREATE OR REPLACE FUNCTION private.fin_effective_limit(p_user UUID)
RETURNS NUMERIC
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
  SELECT CASE
           WHEN u.approval_limit IS NOT NULL THEN u.approval_limit
           WHEN private.user_has_role(p_user, 'project_manager') OR private.user_has_role(p_user, 'executive')
                OR private.user_has_role(p_user, 'admin') THEN NULL
           ELSE COALESCE((SELECT (value #>> '{}')::numeric FROM public.financial_settings
                           WHERE setting_key = 'default_field_approval_limit'), 5000)
         END
    FROM public.users u WHERE u.id = p_user;
$$;

-- The contract behind a line: retainage %, payment terms, number.
CREATE OR REPLACE FUNCTION private.fin_line_contract(p_line_id UUID)
RETURNS public.contracts
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  SELECT c.* FROM public.budget_lines b
    JOIN public.contracts c ON c.id = b.contract_id
                            OR (b.contract_id IS NULL AND c.award_id = b.award_id AND c.status <> 'terminated')
   WHERE b.id = p_line_id
   ORDER BY (c.id = b.contract_id) DESC, c.created_at DESC
   LIMIT 1;
$$;

-- Line roll-up of its latest live payment request.
CREATE OR REPLACE FUNCTION private.fin_rollup_line_approval(p_line_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_status TEXT;
BEGIN
  SELECT status INTO v_status FROM public.payment_approvals
   WHERE budget_line_id = p_line_id AND status <> 'cancelled'
   ORDER BY created_at DESC LIMIT 1;
  UPDATE public.budget_lines
     SET approval_state = CASE
           WHEN v_status IS NULL THEN 'not_requested'
           WHEN v_status = 'pending' THEN 'pending'
           WHEN v_status IN ('field_approved', 'awaiting_manager', 'awaiting_executive') THEN 'field_approved'
           WHEN v_status = 'approved' THEN 'manager_approved'
           WHEN v_status = 'sent_to_finance' THEN 'sent_to_finance'
           ELSE 'rejected' END
   WHERE id = p_line_id;
END;
$$;

CREATE OR REPLACE FUNCTION private.fin_payment_event(
  p_pa public.payment_approvals, p_type TEXT, p_actor UUID, p_note TEXT, p_routed UUID DEFAULT NULL
)
RETURNS VOID
LANGUAGE sql
SET search_path = ''
AS $$
  INSERT INTO public.payment_approval_events (payment_approval_id, project_id, event_type, status_after,
                                              actor_user_id, routed_to_user_id, note)
  VALUES (p_pa.id, p_pa.project_id, p_type, p_pa.status, p_actor, p_routed, NULLIF(btrim(COALESCE(p_note, '')), ''));
$$;

CREATE OR REPLACE FUNCTION private.fin_is_approver(p_user UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  SELECT private.user_has_role(p_user, 'field_manager') OR private.user_has_role(p_user, 'project_manager')
      OR private.user_has_role(p_user, 'executive') OR private.user_has_role(p_user, 'admin');
$$;

-- PO number from the configured formats: {CONTRACT} {YYYY} {MM} {SEQ:n}.
CREATE OR REPLACE FUNCTION private.fin_next_po_number(p_contract TEXT)
RETURNS TEXT
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_fmt    TEXT;
  v_width  INT;
  v_prefix TEXT;
  v_suffix TEXT;
  v_seq    INT;
  v_po     TEXT;
BEGIN
  IF p_contract IS NOT NULL THEN
    v_fmt := COALESCE((SELECT value #>> '{}' FROM public.financial_settings WHERE setting_key = 'po_number_format_contract'),
                      '{CONTRACT}-{SEQ:03}');
  ELSE
    v_fmt := COALESCE((SELECT value #>> '{}' FROM public.financial_settings WHERE setting_key = 'po_number_format'),
                      'PO-{YYYY}-{SEQ:05}');
  END IF;
  IF v_fmt !~ '\{SEQ(:\d+)?\}' THEN
    v_fmt := v_fmt || '-{SEQ:03}';
  END IF;
  v_fmt := replace(replace(replace(v_fmt, '{CONTRACT}', COALESCE(p_contract, '')),
                           '{YYYY}', to_char(CURRENT_DATE, 'YYYY')), '{MM}', to_char(CURRENT_DATE, 'MM'));
  v_width  := COALESCE((regexp_match(v_fmt, '\{SEQ:(\d+)\}'))[1]::int, 1);
  v_prefix := split_part(regexp_replace(v_fmt, '\{SEQ(:\d+)?\}', '#SEQ#'), '#SEQ#', 1);
  v_suffix := split_part(regexp_replace(v_fmt, '\{SEQ(:\d+)?\}', '#SEQ#'), '#SEQ#', 2);

  PERFORM pg_advisory_xact_lock(hashtext('bluonx.po_number'));
  SELECT count(*) + 1 INTO v_seq FROM public.finance_handoffs
   WHERE left(po_number, length(v_prefix)) = v_prefix;
  LOOP
    v_po := left(v_prefix || lpad(v_seq::text, v_width, '0') || v_suffix, 50);
    EXIT WHEN NOT EXISTS (SELECT 1 FROM public.finance_handoffs WHERE po_number = v_po);
    v_seq := v_seq + 1;
  END LOOP;
  RETURN v_po;
END;
$$;


-- ============================================================================
-- SECTION D: 6.1 REQUEST
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_request_payment(
  p_line_id  UUID,
  p_actor    UUID,
  p_kind     TEXT,
  p_percent  NUMERIC,
  p_note     TEXT
)
RETURNS SETOF public.payment_approvals
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_line      public.budget_lines;
  v_contract  public.contracts;
  v_variance  public.variance_lines;
  v_total     NUMERIC;
  v_used      NUMERIC;
  v_gross     NUMERIC;
  v_ret       NUMERIC := 0;
  v_amount    NUMERIC;
  v_vendor    UUID;
  v_pa        public.payment_approvals;
BEGIN
  IF p_kind IS NULL OR p_kind NOT IN ('full', 'progress', 'retainage_release') THEN
    RAISE EXCEPTION 'Choose a full payment, a progress payment or a retainage release.' USING ERRCODE = 'PT422';
  END IF;
  IF NOT private.fin_is_approver(p_actor) THEN
    RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can request a payment.' USING ERRCODE = 'PT403';
  END IF;

  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id;
  IF NOT FOUND OR v_line.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'Budget line % not found', p_line_id USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_line.project_id, FALSE, TRUE);
  SELECT * INTO v_line FROM public.budget_lines WHERE id = p_line_id FOR UPDATE;

  IF v_line.line_type = 'bid_activity' THEN
    IF v_line.award_id IS NULL OR v_line.committed_amount <= 0 THEN
      RAISE EXCEPTION 'This line has no award yet, so there is nothing to pay.' USING ERRCODE = 'PT422';
    END IF;
    v_total    := v_line.committed_amount;
    v_contract := private.fin_line_contract(p_line_id);
    v_ret      := COALESCE(v_contract.retainage_percent, 0);
    SELECT vendor_id INTO v_vendor FROM public.awards WHERE id = v_line.award_id;
  ELSIF v_line.line_type = 'variance' THEN
    SELECT * INTO v_variance FROM public.variance_lines WHERE budget_line_id = p_line_id;
    IF v_variance.status IS DISTINCT FROM 'pending_approval' THEN
      RAISE EXCEPTION 'Only a variance waiting for approval can be sent for payment.' USING ERRCODE = 'PT422';
    END IF;
    IF p_kind <> 'full' THEN
      RAISE EXCEPTION 'A variance is paid in full.' USING ERRCODE = 'PT422';
    END IF;
    v_total  := v_line.budget_amount;
    v_vendor := v_variance.vendor_id;
  ELSE
    RAISE EXCEPTION 'Payments on % lines start from their invoices (Invoices tab).', replace(v_line.line_type, '_', ' ')
      USING ERRCODE = 'PT422';
  END IF;

  IF EXISTS (SELECT 1 FROM public.payment_approvals WHERE budget_line_id = p_line_id
              AND status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive')) THEN
    RAISE EXCEPTION 'This line already has a payment waiting for approval.' USING ERRCODE = 'PT409';
  END IF;

  SELECT COALESCE(SUM(COALESCE(gross_amount, amount)), 0) INTO v_used FROM public.payment_approvals
   WHERE budget_line_id = p_line_id AND status NOT IN ('rejected', 'cancelled') AND payment_kind <> 'retainage_release';

  IF p_kind = 'retainage_release' THEN
    IF v_used < v_total THEN
      RAISE EXCEPTION 'Retainage is released once the whole line has been approved for payment.' USING ERRCODE = 'PT422';
    END IF;
    SELECT COALESCE(SUM(retainage_amount) FILTER (WHERE payment_kind <> 'retainage_release'), 0)
           - COALESCE(SUM(amount) FILTER (WHERE payment_kind = 'retainage_release'), 0)
      INTO v_amount FROM public.payment_approvals
     WHERE budget_line_id = p_line_id AND status NOT IN ('rejected', 'cancelled');
    IF v_amount <= 0 THEN
      RAISE EXCEPTION 'No retainage is held on this line.' USING ERRCODE = 'PT422';
    END IF;
    v_gross := v_amount;
    v_ret   := NULL;
  ELSE
    IF p_kind = 'full' THEN
      v_gross := v_total - v_used;
    ELSE
      IF p_percent IS NULL OR p_percent <= 0 OR p_percent > 100 THEN
        RAISE EXCEPTION 'Enter a progress %% above 0 and up to 100.' USING ERRCODE = 'PT422';
      END IF;
      v_gross := round(v_total * p_percent / 100, 2);
    END IF;
    IF v_gross <= 0 THEN
      RAISE EXCEPTION 'This line is already fully approved for payment.' USING ERRCODE = 'PT422';
    END IF;
    IF v_gross > v_total - v_used THEN
      RAISE EXCEPTION 'That is more than is left to pay on this line (%).', v_total - v_used USING ERRCODE = 'PT422';
    END IF;
    v_ret    := round(v_gross * v_ret / 100, 2);
    v_amount := v_gross - v_ret;
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  INSERT INTO public.payment_approvals (
    project_id, budget_line_id, vendor_id, amount, gross_amount, payment_kind, progress_percent,
    retainage_amount, status, requested_by, comments
  ) VALUES (
    v_line.project_id, p_line_id, v_vendor, v_amount, v_gross, p_kind,
    CASE WHEN p_kind = 'progress' THEN p_percent END, NULLIF(v_ret, 0), 'pending', p_actor,
    NULLIF(btrim(COALESCE(p_note, '')), '')
  ) RETURNING * INTO v_pa;
  PERFORM private.fin_payment_event(v_pa, 'requested', p_actor, p_note);
  PERFORM private.fin_rollup_line_approval(p_line_id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_pa;
END;
$$;

COMMENT ON FUNCTION public.fn_request_payment(UUID, UUID, TEXT, NUMERIC, TEXT) IS
  'Starts a payment on a bid or variance line: full (what is left), progress (% of the line) or retainage release (after the line is fully paid). Retainage follows the contract.';


-- ============================================================================
-- SECTION E: 6.2 / 6.3 APPROVAL STEP
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_payment_approval_step(
  p_id               UUID,
  p_actor            UUID,
  p_expected_status  TEXT,
  p_step             TEXT,
  p_next_status      TEXT,
  p_routed_to        UUID,
  p_note             TEXT,
  p_work_confirmed   BOOLEAN
)
RETURNS JSONB
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_pa        public.payment_approvals;
  v_project   UUID;
  v_actor     public.users;
  v_line      public.budget_lines;
  v_variance  public.variance_lines;
  v_contract  public.contracts;
  v_gross     NUMERIC;
  v_limit     NUMERIC;
  v_threshold NUMERIC;
  v_terms     INT;
  v_handoff   UUID;
  v_po        TEXT;
  v_names     JSONB;
BEGIN
  SELECT project_id INTO v_project FROM public.payment_approvals WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Payment approval not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_project, FALSE, FALSE);
  SELECT * INTO v_pa FROM public.payment_approvals WHERE id = p_id FOR UPDATE;
  IF v_pa.status IS DISTINCT FROM p_expected_status THEN
    RAISE EXCEPTION 'This payment changed a moment ago (now %). Reload and try again.', replace(v_pa.status, '_', ' ')
      USING ERRCODE = 'PT409';
  END IF;

  SELECT * INTO v_actor FROM public.users WHERE id = p_actor AND is_active AND deleted_at IS NULL;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Your account is not active.' USING ERRCODE = 'PT403';
  END IF;
  SELECT * INTO v_line FROM public.budget_lines WHERE id = v_pa.budget_line_id FOR UPDATE;
  SELECT * INTO v_variance FROM public.variance_lines WHERE budget_line_id = v_line.id;
  IF v_variance.created_by = p_actor THEN
    RAISE EXCEPTION 'You created this variance, so a different person must approve it.' USING ERRCODE = 'PT403';
  END IF;

  v_gross     := COALESCE(v_pa.gross_amount, v_pa.amount);
  v_threshold := (SELECT (value #>> '{}')::numeric FROM public.financial_settings
                   WHERE setting_key = 'executive_approval_threshold' AND jsonb_typeof(value) = 'number');

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);

  IF p_step = 'field' THEN
    IF v_pa.status <> 'pending' OR p_next_status NOT IN ('awaiting_manager', 'awaiting_executive', 'approved') THEN
      RAISE EXCEPTION 'Work confirmation is the first step.' USING ERRCODE = 'PT409';
    END IF;
    IF NOT COALESCE(p_work_confirmed, FALSE) THEN
      RAISE EXCEPTION 'Confirm the work is complete before approving.' USING ERRCODE = 'PT422';
    END IF;
    IF NOT private.fin_is_approver(p_actor) THEN
      RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can confirm work.' USING ERRCODE = 'PT403';
    END IF;
    IF NOT v_actor.is_employee AND p_next_status <> 'awaiting_manager' THEN
      RAISE EXCEPTION 'External field managers can confirm work but never authorise payment.' USING ERRCODE = 'PT403';
    END IF;
    UPDATE public.payment_approvals
       SET work_confirmed_by = p_actor, work_confirmed_at = NOW(),
           field_approved_by = p_actor, field_approved_at = NOW(),
           confirmed_by_external = NOT v_actor.is_employee
     WHERE id = p_id RETURNING * INTO v_pa;
    PERFORM private.fin_payment_event(v_pa, 'work_confirmed', p_actor, p_note);
  ELSIF p_step = 'manager' THEN
    IF v_pa.status <> 'awaiting_manager' OR p_next_status NOT IN ('awaiting_executive', 'approved') THEN
      RAISE EXCEPTION 'This payment is not waiting for a manager.' USING ERRCODE = 'PT409';
    END IF;
    IF NOT v_actor.is_employee THEN
      RAISE EXCEPTION 'Only internal employees can authorise payment.' USING ERRCODE = 'PT403';
    END IF;
    IF p_actor IN (v_pa.field_approved_by, v_pa.work_confirmed_by) THEN
      RAISE EXCEPTION 'You gave the first approval, so a different person must give the second.' USING ERRCODE = 'PT403';
    END IF;
    IF NOT (private.user_has_role(p_actor, 'project_manager') OR private.user_has_role(p_actor, 'executive')
            OR private.user_has_role(p_actor, 'admin') OR p_actor = v_pa.routed_to_user_id) THEN
      RAISE EXCEPTION 'Only a manager can give the second approval.' USING ERRCODE = 'PT403';
    END IF;
    IF v_actor.approval_limit IS NOT NULL AND v_gross > v_actor.approval_limit THEN
      RAISE EXCEPTION 'This amount is above your approval limit of %.', v_actor.approval_limit USING ERRCODE = 'PT403';
    END IF;
    UPDATE public.payment_approvals SET manager_approved_by = p_actor, manager_approved_at = NOW()
     WHERE id = p_id RETURNING * INTO v_pa;
    PERFORM private.fin_payment_event(v_pa, 'manager_approved', p_actor, p_note);
  ELSIF p_step = 'executive' THEN
    IF v_pa.status <> 'awaiting_executive' OR p_next_status <> 'approved' THEN
      RAISE EXCEPTION 'This payment is not waiting for an executive.' USING ERRCODE = 'PT409';
    END IF;
    IF NOT v_actor.is_employee OR NOT private.user_has_role(p_actor, 'executive') THEN
      RAISE EXCEPTION 'Only an internal executive can give the executive approval.' USING ERRCODE = 'PT403';
    END IF;
    IF p_actor IN (v_pa.field_approved_by, v_pa.work_confirmed_by, v_pa.manager_approved_by) THEN
      RAISE EXCEPTION 'You already approved this payment, so a different executive must approve it.' USING ERRCODE = 'PT403';
    END IF;
    UPDATE public.payment_approvals SET executive_approved_by = p_actor, executive_approved_at = NOW()
     WHERE id = p_id RETURNING * INTO v_pa;
    PERFORM private.fin_payment_event(v_pa, 'executive_approved', p_actor, p_note);
  ELSE
    RAISE EXCEPTION 'Unknown approval step %', p_step USING ERRCODE = 'PT422';
  END IF;

  -- The rules that must hold whatever the caller decided.
  IF p_next_status IN ('awaiting_executive', 'approved') THEN
    v_limit := private.fin_effective_limit(v_pa.field_approved_by);
    IF (v_pa.confirmed_by_external OR (v_limit IS NOT NULL AND v_gross > v_limit)) AND v_pa.manager_approved_by IS NULL THEN
      RAISE EXCEPTION 'This payment needs a second approval by a manager.' USING ERRCODE = 'PT422';
    END IF;
  END IF;
  IF p_next_status = 'approved' AND v_threshold IS NOT NULL AND v_gross > v_threshold
     AND v_pa.executive_approved_by IS NULL THEN
    RAISE EXCEPTION 'This payment is above the executive threshold and needs an executive approval.' USING ERRCODE = 'PT422';
  END IF;

  UPDATE public.payment_approvals
     SET status = p_next_status,
         routed_to_user_id = CASE WHEN p_next_status IN ('awaiting_manager', 'awaiting_executive') THEN p_routed_to END,
         executive_required = v_threshold IS NOT NULL AND v_gross > v_threshold,
         comments = COALESCE(NULLIF(btrim(COALESCE(p_note, '')), ''), comments)
   WHERE id = p_id RETURNING * INTO v_pa;

  IF p_next_status = 'awaiting_manager' THEN
    PERFORM private.fin_payment_event(v_pa, 'routed_to_manager', p_actor, NULL, p_routed_to);
  ELSIF p_next_status = 'awaiting_executive' THEN
    PERFORM private.fin_payment_event(v_pa, 'routed_to_executive', p_actor, NULL, p_routed_to);
  ELSE
    -- 6.4 / 6.5: final approval.
    v_contract := private.fin_line_contract(v_line.id);
    v_terms := COALESCE(v_contract.payment_terms_days, v_line.payment_terms_days);
    UPDATE public.payment_approvals
       SET approved_at = NOW(), expected_payment_date = CURRENT_DATE + v_terms
     WHERE id = p_id RETURNING * INTO v_pa;

    INSERT INTO public.cash_flow_entries (project_id, budget_line_id, payment_approval_id, period_month,
                                          direction, cash_bucket, amount, entry_kind, source_note)
    VALUES (v_pa.project_id, v_line.id, v_pa.id, date_trunc('month', v_pa.expected_payment_date)::date,
            'out', v_line.cash_bucket, v_pa.amount, 'expected', 'Approved payment, expected ' || v_pa.expected_payment_date);

    IF v_variance.id IS NOT NULL AND v_variance.status = 'pending_approval' THEN
      UPDATE public.variance_lines SET status = 'approved', approved_by = p_actor, approved_at = NOW()
       WHERE id = v_variance.id;
      INSERT INTO public.variance_events (variance_id, project_id, event_type, amount_after, actor_user_id, note)
      VALUES (v_variance.id, v_variance.project_id, 'approved', v_line.budget_amount, p_actor, p_note);
    END IF;
    IF v_pa.internal_invoice_id IS NOT NULL AND NOT EXISTS (
         SELECT 1 FROM public.payment_approvals
          WHERE internal_invoice_id = v_pa.internal_invoice_id
            AND status NOT IN ('approved', 'sent_to_finance', 'cancelled')) THEN
      UPDATE public.internal_invoices SET status = 'approved' WHERE id = v_pa.internal_invoice_id;
    END IF;

    SELECT jsonb_object_agg(k, u.full_name) INTO v_names
      FROM (VALUES ('work_confirmed_by', v_pa.work_confirmed_by), ('field_approved_by', v_pa.field_approved_by),
                   ('manager_approved_by', v_pa.manager_approved_by),
                   ('executive_approved_by', v_pa.executive_approved_by)) AS a(k, id)
      JOIN public.users u ON u.id = a.id;

    v_po := private.fin_next_po_number(v_contract.contract_number);
    INSERT INTO public.finance_handoffs (payment_approval_id, project_id, po_number, vendor_id, amount, payload, status)
    SELECT v_pa.id, v_pa.project_id, v_po, v_pa.vendor_id, v_pa.amount,
           jsonb_build_object(
             'po_number', v_po,
             'project', p.name,
             'line', v_line.name,
             'line_type', v_line.line_type,
             'trade', COALESCE(tr.name, vt.name),
             'vendor', COALESCE(vd.company_name, inv.payee_name),
             'invoice_number', inv.invoice_number,
             'contract_number', v_contract.contract_number,
             'payment_kind', v_pa.payment_kind,
             'progress_percent', v_pa.progress_percent,
             'gross_amount', COALESCE(v_pa.gross_amount, v_pa.amount),
             'retainage_amount', COALESCE(v_pa.retainage_amount, 0),
             'amount', v_pa.amount,
             'approved_on', CURRENT_DATE,
             'expected_payment_date', v_pa.expected_payment_date,
             'payment_terms_days', v_terms,
             'approvers', COALESCE(v_names, '{}'::jsonb)),
           'pending'
      FROM public.projects p
      LEFT JOIN public.tasks t ON t.id = COALESCE(v_line.task_id, (SELECT task_id FROM public.budget_lines WHERE id = v_line.parent_line_id))
      LEFT JOIN public.trades tr ON tr.id = t.trade_id
      LEFT JOIN public.trades vt ON vt.id = v_variance.trade_id
      LEFT JOIN public.vendors vd ON vd.id = v_pa.vendor_id
      LEFT JOIN public.internal_invoices inv ON inv.id = v_pa.internal_invoice_id
     WHERE p.id = v_pa.project_id
    RETURNING id INTO v_handoff;

    PERFORM private.fin_payment_event(v_pa, 'approved', p_actor, 'PO ' || v_po);
  END IF;

  PERFORM private.fin_rollup_line_approval(v_line.id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);

  RETURN jsonb_build_object('id', v_pa.id, 'status', v_pa.status, 'routed_to_user_id', v_pa.routed_to_user_id,
                            'handoff_id', v_handoff, 'po_number', v_po);
END;
$$;

COMMENT ON FUNCTION public.fn_payment_approval_step(UUID, UUID, TEXT, TEXT, TEXT, UUID, TEXT, BOOLEAN) IS
  'Records one approval step decided by app/services/payment_rules.py and re-checks the hard rules. Final approval writes the expected cash-flow entry, approves the variance / invoice and creates the finance hand-off with its PO number.';


-- ============================================================================
-- SECTION F: REJECT / RESUBMIT / CANCEL
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_reject_payment(p_id UUID, p_actor UUID, p_reason TEXT)
RETURNS SETOF public.payment_approvals
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_pa       public.payment_approvals;
  v_project  UUID;
  v_variance public.variance_lines;
BEGIN
  IF btrim(COALESCE(p_reason, '')) = '' THEN
    RAISE EXCEPTION 'A rejection needs a reason.' USING ERRCODE = 'PT422';
  END IF;
  SELECT project_id INTO v_project FROM public.payment_approvals WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Payment approval not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_project, FALSE, FALSE);
  SELECT * INTO v_pa FROM public.payment_approvals WHERE id = p_id FOR UPDATE;
  IF v_pa.status NOT IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive') THEN
    RAISE EXCEPTION 'This payment is % and cannot be rejected.', replace(v_pa.status, '_', ' ') USING ERRCODE = 'PT409';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = p_actor AND is_active AND is_employee AND deleted_at IS NULL) THEN
    RAISE EXCEPTION 'Only internal employees can reject a payment.' USING ERRCODE = 'PT403';
  END IF;
  IF NOT (private.fin_is_approver(p_actor) OR p_actor = v_pa.routed_to_user_id) THEN
    RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can reject a payment.' USING ERRCODE = 'PT403';
  END IF;
  SELECT * INTO v_variance FROM public.variance_lines WHERE budget_line_id = v_pa.budget_line_id;
  IF v_variance.created_by = p_actor THEN
    RAISE EXCEPTION 'You created this variance: edit or cancel it instead of rejecting it.' USING ERRCODE = 'PT403';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.payment_approvals
     SET status = 'rejected', rejected_by = p_actor, rejected_at = NOW(), rejection_reason = btrim(p_reason),
         routed_to_user_id = NULL
   WHERE id = p_id RETURNING * INTO v_pa;
  IF v_variance.id IS NOT NULL AND v_variance.status = 'pending_approval' THEN
    UPDATE public.variance_lines
       SET status = 'rejected', rejected_by = p_actor, rejected_at = NOW(), rejection_reason = btrim(p_reason)
     WHERE id = v_variance.id;
    INSERT INTO public.variance_events (variance_id, project_id, event_type, actor_user_id, note)
    VALUES (v_variance.id, v_variance.project_id, 'rejected', p_actor, btrim(p_reason));
  END IF;
  IF v_pa.internal_invoice_id IS NOT NULL THEN
    UPDATE public.internal_invoices SET status = 'rejected' WHERE id = v_pa.internal_invoice_id;
  END IF;
  PERFORM private.fin_payment_event(v_pa, 'rejected', p_actor, p_reason);
  PERFORM private.fin_rollup_line_approval(v_pa.budget_line_id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_pa;
END;
$$;

-- A rejected payment goes back to the field manager, who fixes it and sends a
-- copy (same amounts) for approval again. Variances resubmit by being edited.
CREATE OR REPLACE FUNCTION public.fn_resubmit_payment(p_id UUID, p_actor UUID, p_note TEXT)
RETURNS SETOF public.payment_approvals
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_old public.payment_approvals;
  v_new public.payment_approvals;
BEGIN
  SELECT * INTO v_old FROM public.payment_approvals WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Payment approval not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_old.project_id, FALSE, TRUE);
  SELECT * INTO v_old FROM public.payment_approvals WHERE id = p_id FOR UPDATE;
  IF v_old.status <> 'rejected' THEN
    RAISE EXCEPTION 'Only a rejected payment can be resubmitted.' USING ERRCODE = 'PT409';
  END IF;
  IF NOT private.fin_is_approver(p_actor) THEN
    RAISE EXCEPTION 'Only a field manager, project manager, executive or admin can resubmit a payment.' USING ERRCODE = 'PT403';
  END IF;
  IF EXISTS (SELECT 1 FROM public.variance_lines WHERE budget_line_id = v_old.budget_line_id) THEN
    RAISE EXCEPTION 'Edit the variance to resubmit it.' USING ERRCODE = 'PT422';
  END IF;
  IF EXISTS (SELECT 1 FROM public.payment_approvals WHERE budget_line_id = v_old.budget_line_id
              AND status IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive')) THEN
    RAISE EXCEPTION 'This line already has a payment waiting for approval.' USING ERRCODE = 'PT409';
  END IF;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  INSERT INTO public.payment_approvals (
    project_id, budget_line_id, internal_invoice_id, vendor_id, amount, gross_amount, payment_kind,
    progress_percent, retainage_amount, status, requested_by, comments, resubmitted_from
  ) VALUES (
    v_old.project_id, v_old.budget_line_id, v_old.internal_invoice_id, v_old.vendor_id, v_old.amount,
    v_old.gross_amount, v_old.payment_kind, v_old.progress_percent, v_old.retainage_amount, 'pending', p_actor,
    COALESCE(NULLIF(btrim(COALESCE(p_note, '')), ''), v_old.comments), v_old.id
  ) RETURNING * INTO v_new;
  IF v_new.internal_invoice_id IS NOT NULL THEN
    UPDATE public.internal_invoices SET status = 'in_approval' WHERE id = v_new.internal_invoice_id;
  END IF;
  PERFORM private.fin_payment_event(v_new, 'resubmitted', p_actor, p_note);
  PERFORM private.fin_rollup_line_approval(v_new.budget_line_id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_new;
END;
$$;

CREATE OR REPLACE FUNCTION public.fn_cancel_payment(p_id UUID, p_actor UUID, p_note TEXT)
RETURNS SETOF public.payment_approvals
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_pa public.payment_approvals;
BEGIN
  SELECT * INTO v_pa FROM public.payment_approvals WHERE id = p_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Payment approval not found' USING ERRCODE = 'PT404';
  END IF;
  PERFORM private.fin_lock_project(v_pa.project_id, FALSE, FALSE);
  SELECT * INTO v_pa FROM public.payment_approvals WHERE id = p_id FOR UPDATE;
  IF v_pa.status NOT IN ('pending', 'field_approved', 'awaiting_manager', 'awaiting_executive', 'rejected') THEN
    RAISE EXCEPTION 'This payment is % and cannot be withdrawn.', replace(v_pa.status, '_', ' ') USING ERRCODE = 'PT409';
  END IF;
  IF v_pa.internal_invoice_id IS NOT NULL
     OR EXISTS (SELECT 1 FROM public.variance_lines WHERE budget_line_id = v_pa.budget_line_id) THEN
    RAISE EXCEPTION 'Invoice and variance payments are withdrawn by cancelling the invoice or the variance.' USING ERRCODE = 'PT422';
  END IF;
  IF p_actor <> v_pa.requested_by AND NOT (private.user_has_role(p_actor, 'project_manager')
                                           OR private.user_has_role(p_actor, 'admin')) THEN
    RAISE EXCEPTION 'Only the person who asked for the payment, a project manager or an admin can withdraw it.' USING ERRCODE = 'PT403';
  END IF;
  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.payment_approvals SET status = 'cancelled', routed_to_user_id = NULL
   WHERE id = p_id RETURNING * INTO v_pa;
  PERFORM private.fin_payment_event(v_pa, 'cancelled', p_actor, p_note);
  PERFORM private.fin_rollup_line_approval(v_pa.budget_line_id);
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_pa;
END;
$$;


-- ============================================================================
-- SECTION G: 6.6 HAND-OFF DELIVERED
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_mark_finance_handoff(
  p_handoff_id   UUID,
  p_sent         BOOLEAN,
  p_email_log_id UUID,
  p_document     TEXT,
  p_error        TEXT
)
RETURNS SETOF public.finance_handoffs
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
  v_h  public.finance_handoffs;
  v_pa public.payment_approvals;
BEGIN
  SELECT * INTO v_h FROM public.finance_handoffs WHERE id = p_handoff_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Hand-off not found' USING ERRCODE = 'PT404';
  END IF;
  UPDATE public.finance_handoffs
     SET document_path = COALESCE(p_document, document_path),
         email_log_id  = COALESCE(p_email_log_id, email_log_id),
         status        = CASE WHEN p_sent THEN 'sent' WHEN status = 'sent' THEN status ELSE 'failed' END,
         sent_at       = CASE WHEN p_sent THEN COALESCE(sent_at, NOW()) ELSE sent_at END,
         handoff_error = CASE WHEN p_sent THEN NULL ELSE p_error END
   WHERE id = p_handoff_id RETURNING * INTO v_h;

  PERFORM set_config('bluonx.financial_write', 'on', TRUE);
  UPDATE public.payment_approvals SET status = 'sent_to_finance'
   WHERE id = v_h.payment_approval_id AND status = 'approved' AND p_sent
   RETURNING * INTO v_pa;
  IF v_pa.id IS NOT NULL THEN
    PERFORM private.fin_payment_event(v_pa, 'sent_to_finance', NULL, 'PO ' || v_h.po_number);
    PERFORM private.fin_rollup_line_approval(v_pa.budget_line_id);
  ELSIF NOT p_sent THEN
    SELECT * INTO v_pa FROM public.payment_approvals WHERE id = v_h.payment_approval_id;
    PERFORM private.fin_payment_event(v_pa, 'handoff_failed', NULL, p_error);
  END IF;
  PERFORM set_config('bluonx.financial_write', 'off', TRUE);
  RETURN NEXT v_h;
END;
$$;


-- ============================================================================
-- SECTION H: READ SURFACE
-- ============================================================================
CREATE OR REPLACE VIEW public.v_payment_approvals
WITH (security_invoker = true) AS
SELECT pa.id, pa.project_id, p.name AS project_name, p.status AS project_status,
       pa.budget_line_id, bl.name AS line_name, bl.line_type, bl.committed_amount AS line_committed,
       bl.budget_amount AS line_budget, bl.payment_terms_days,
       COALESCE(tr.name, vt.name) AS trade_name,
       pa.vendor_id, COALESCE(vd.company_name, inv.payee_name) AS vendor_name,
       pa.internal_invoice_id, inv.invoice_number,
       vl.id AS variance_id, vl.created_by AS variance_created_by,
       c.contract_number, c.retainage_percent,
       pa.amount, COALESCE(pa.gross_amount, pa.amount) AS gross_amount, COALESCE(pa.retainage_amount, 0) AS retainage_amount,
       pa.payment_kind, pa.progress_percent, pa.status, pa.comments,
       pa.requested_by, ru.full_name AS requested_by_name, pa.created_at,
       pa.work_confirmed_by, wu.full_name AS work_confirmed_by_name, pa.work_confirmed_at, pa.confirmed_by_external,
       pa.field_approved_by, fu.full_name AS field_approved_by_name, pa.field_approved_at,
       pa.routed_to_user_id, tu.full_name AS routed_to_name,
       pa.manager_approved_by, mu.full_name AS manager_approved_by_name, pa.manager_approved_at,
       pa.executive_required, pa.executive_approved_by, eu.full_name AS executive_approved_by_name, pa.executive_approved_at,
       pa.rejected_by, xu.full_name AS rejected_by_name, pa.rejected_at, pa.rejection_reason,
       pa.approved_at, pa.expected_payment_date, pa.resubmitted_from,
       fh.id AS handoff_id, fh.po_number, fh.status AS handoff_status, fh.sent_at AS handoff_sent_at,
       el.status AS handoff_delivery_status, pa.updated_at
  FROM public.payment_approvals pa
  JOIN public.projects p ON p.id = pa.project_id AND p.deleted_at IS NULL
  JOIN public.budget_lines bl ON bl.id = pa.budget_line_id
  LEFT JOIN public.variance_lines vl ON vl.budget_line_id = bl.id
  LEFT JOIN public.tasks t ON t.id = COALESCE(bl.task_id, (SELECT b2.task_id FROM public.budget_lines b2 WHERE b2.id = bl.parent_line_id))
  LEFT JOIN public.trades tr ON tr.id = t.trade_id
  LEFT JOIN public.trades vt ON vt.id = vl.trade_id
  LEFT JOIN public.vendors vd ON vd.id = pa.vendor_id
  LEFT JOIN public.internal_invoices inv ON inv.id = pa.internal_invoice_id
  LEFT JOIN LATERAL (SELECT * FROM private.fin_line_contract(bl.id)) c ON TRUE
  LEFT JOIN public.users ru ON ru.id = pa.requested_by
  LEFT JOIN public.users wu ON wu.id = pa.work_confirmed_by
  LEFT JOIN public.users fu ON fu.id = pa.field_approved_by
  LEFT JOIN public.users tu ON tu.id = pa.routed_to_user_id
  LEFT JOIN public.users mu ON mu.id = pa.manager_approved_by
  LEFT JOIN public.users eu ON eu.id = pa.executive_approved_by
  LEFT JOIN public.users xu ON xu.id = pa.rejected_by
  LEFT JOIN public.finance_handoffs fh ON fh.payment_approval_id = pa.id
  LEFT JOIN public.email_log el ON el.id = fh.email_log_id;

COMMENT ON VIEW public.v_payment_approvals IS
  'Payment approvals with project, line, trade, vendor, contract, every approver and the finance hand-off. security_invoker = true.';

CREATE OR REPLACE VIEW public.v_finance_handoffs
WITH (security_invoker = true) AS
SELECT fh.id, fh.payment_approval_id, fh.project_id, p.name AS project_name, fh.po_number, fh.vendor_id,
       fh.amount, fh.payload, fh.document_path, fh.status, fh.sent_at, fh.exported_at, fh.handoff_error,
       fh.email_log_id, el.recipient_email AS delivered_to, el.status AS delivery_status, el.sent_at AS email_sent_at,
       fh.created_at
  FROM public.finance_handoffs fh
  JOIN public.projects p ON p.id = fh.project_id AND p.deleted_at IS NULL
  LEFT JOIN public.email_log el ON el.id = fh.email_log_id;

COMMENT ON VIEW public.v_finance_handoffs IS
  'Finance hand-off log with the email_log delivery status of each PO. security_invoker = true.';


-- ============================================================================
-- SECTION I: PRIVILEGES
-- ============================================================================
REVOKE ALL ON public.v_payment_approvals, public.v_finance_handoffs FROM PUBLIC, anon;
GRANT SELECT ON public.v_payment_approvals TO authenticated, service_role;
GRANT SELECT ON public.v_finance_handoffs TO service_role;

REVOKE ALL ON FUNCTION private.fin_effective_limit(uuid)          FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.fin_line_contract(uuid)            FROM PUBLIC, anon;
REVOKE ALL ON FUNCTION private.fin_is_approver(uuid)              FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION private.fin_effective_limit(uuid)       TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.fin_line_contract(uuid)         TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION private.fin_is_approver(uuid)           TO authenticated, service_role;
REVOKE ALL ON FUNCTION private.fin_rollup_line_approval(uuid)     FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_next_po_number(text)           FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION private.fin_payment_event(public.payment_approvals, text, uuid, text, uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION private.fin_rollup_line_approval(uuid)  TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_next_po_number(text)        TO service_role;
GRANT EXECUTE ON FUNCTION private.fin_payment_event(public.payment_approvals, text, uuid, text, uuid) TO service_role;

REVOKE ALL ON FUNCTION public.fn_block_payment_event_mutation() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_request_payment(uuid, uuid, text, numeric, text)                          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_payment_approval_step(uuid, uuid, text, text, text, uuid, text, boolean)  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_reject_payment(uuid, uuid, text)                                          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_resubmit_payment(uuid, uuid, text)                                        FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_cancel_payment(uuid, uuid, text)                                          FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fn_mark_finance_handoff(uuid, boolean, uuid, text, text)                     FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_request_payment(uuid, uuid, text, numeric, text)                       TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_payment_approval_step(uuid, uuid, text, text, text, uuid, text, boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_reject_payment(uuid, uuid, text)                                       TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_resubmit_payment(uuid, uuid, text)                                     TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_cancel_payment(uuid, uuid, text)                                       TO service_role;
GRANT EXECUTE ON FUNCTION public.fn_mark_finance_handoff(uuid, boolean, uuid, text, text)                  TO service_role;


-- ============================================================================
-- SECTION J: SETTINGS AND VERSION MARKER
-- ============================================================================
INSERT INTO public.financial_settings (setting_key, value, description) VALUES
  ('po_number_format_contract', '"{CONTRACT}-{SEQ:03}"'::jsonb, 'PO number when the line has a contract: the contract number is the default reference. Tokens {CONTRACT} {YYYY} {MM} {SEQ:n}.'),
  ('quickbooks_expense_account', '"Job Expenses"'::jsonb, 'Expense account written on every line of the QuickBooks bill import.')
ON CONFLICT (setting_key) DO NOTHING;

INSERT INTO public.financial_settings (setting_key, value, description)
VALUES ('schema_version', '"4.7.0 (20261127_financial_phase6_payments)"'::jsonb,
        'Last financial migration applied to this database. Written by the migration itself.')
ON CONFLICT (setting_key) DO UPDATE SET value = EXCLUDED.value;

COMMIT;
