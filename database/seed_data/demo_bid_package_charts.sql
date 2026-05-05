-- ============================================================================
-- BluOnX — Demo Seed: Bid Package Charts (Task 6.3)
-- ============================================================================
-- Purpose:  Populate ONE bid package on an existing project so the bid package
--           detail page exercises both new charts (status pie + amount bar).
-- Audience: Internal demo to client. Run before the demo, run cleanup after.
-- Safety:   All demo rows use hard-coded UUIDs prefixed `d000d000-...`. Nothing
--           outside those UUIDs is touched. Re-runnable: top of file removes
--           any prior demo rows before seeding fresh.
--
-- ⚠️  THIS IS DEMO DATA. DO NOT RUN IN PRODUCTION.
--
-- Pre-existing rows referenced (NOT modified):
--   PM user           : d2c3a2ed-2443-4c47-a46b-2db3b4b60c73   (admin)
--   Project           : 3bb30c5d-1bc6-45eb-9ce9-a044b92bdb8b   (Austin Development Site)
--   Trade             : 3fcb4eba-0389-4682-838d-5c72b2fc6ec4   (Engineering)
--   Bid template      : 3417c2ef-2787-47bc-8a29-e62176a27c26   (Grading & Earthwork Breakdown)
--   7 Engineering vendors + their primary contacts (see VALUES below)
--
-- What this creates (all under the d000d000-... namespace):
--   1 task          — "Demo: Civil Engineering Package" with $50k budget
--   1 bid_package   — open, deadline 14 days out
--   7 invitations   — 3 submitted, 1 opened, 1 sent, 1 declined, 1 expired
--   3 submissions   — $41,200 / $47,500 / $52,800 (one above the $50k budget)
--
-- Trigger note: inserting a bid_submissions row with status='submitted' fires
-- `fn_sync_bid_invitation_on_submission`, which overwrites the parent
-- bid_invitations.responded_at with NOW(). This is fine for a demo; the dates
-- on the 3 submitted rows will read "today" rather than the historical value
-- set in the INSERT below.
-- ============================================================================

BEGIN;

-- ── 0. IDEMPOTENCY: remove any prior demo rows under our UUID namespace ──
--    Order matters: children first (bid_submissions → bid_invitations →
--    bid_packages → tasks). magic_link_tokens cascade-delete via FK.

DELETE FROM bid_submissions
 WHERE bid_invitation_id IN (
   SELECT id FROM bid_invitations
    WHERE bid_package_id = 'd000d000-0000-0000-0000-000000000002'
 );

DELETE FROM bid_invitations
 WHERE bid_package_id = 'd000d000-0000-0000-0000-000000000002';

DELETE FROM bid_packages
 WHERE id = 'd000d000-0000-0000-0000-000000000002';

DELETE FROM tasks
 WHERE id = 'd000d000-0000-0000-0000-000000000001';


-- ── 1. Demo task ─────────────────────────────────────────────────────────
--    Attached to "Austin Development Site". Engineering trade. $50k budget
--    so the $52,800 bar visibly exceeds the (future) budget reference line.

INSERT INTO tasks (
  id, project_id, trade_id, name, description,
  phase, bid_type, budget_estimate, sort_order, status, created_by
) VALUES (
  'd000d000-0000-0000-0000-000000000001',
  '3bb30c5d-1bc6-45eb-9ce9-a044b92bdb8b',
  '3fcb4eba-0389-4682-838d-5c72b2fc6ec4',
  'Demo: Civil Engineering Package',
  'Synthetic task for client demo of the bid package detail page charts. Safe to delete via the cleanup block at the bottom of this file.',
  'development',
  'competitive',
  50000.00,
  999,
  'bidding',
  'd2c3a2ed-2443-4c47-a46b-2db3b4b60c73'
);


-- ── 2. Demo bid_package ──────────────────────────────────────────────────
--    round_number is auto-set by trigger fn_set_bid_package_round_number
--    to MAX(round_number)+1 for this task — will be 1 since the task is new.
--    Deadline 14 days out so lazy-expiration (`expire_overdue_invitations`)
--    won't kick in when you open the page.

INSERT INTO bid_packages (
  id, task_id, deadline, instructions, status,
  bid_template_id, created_by
) VALUES (
  'd000d000-0000-0000-0000-000000000002',
  'd000d000-0000-0000-0000-000000000001',
  NOW() + INTERVAL '14 days',
  'Demo bid package. Lump sum or unit pricing accepted. Mobilization as separate line item. Bids held firm 30 days.',
  'open',
  '3417c2ef-2787-47bc-8a29-e62176a27c26',
  'd2c3a2ed-2443-4c47-a46b-2db3b4b60c73'
);


-- ── 3. 7 invitations across all 5 statuses ───────────────────────────────
--    Pie chart slices = sent + opened + submitted + declined + expired.
--    Distribution: 3 submitted, 1 opened, 1 sent, 1 declined, 1 expired.

INSERT INTO bid_invitations (
  id, bid_package_id, vendor_id, vendor_contact_id,
  status, sent_at, opened_at, responded_at
) VALUES
  -- ── 3 submitted (these will get bid_submissions rows below) ──
  ('d000d000-0000-0000-0000-000000000101',
   'd000d000-0000-0000-0000-000000000002',
   'ae788094-19b5-405f-aa0e-e71f6a7a5208',  -- AquaFlow Irrigation Systems
   '7e19df5a-5903-4313-b520-08a36fe201d9',
   'submitted', NOW() - INTERVAL '3 days', NOW() - INTERVAL '2 days', NOW() - INTERVAL '1 day'),

  ('d000d000-0000-0000-0000-000000000102',
   'd000d000-0000-0000-0000-000000000002',
   'dcb1bf07-dee8-4710-810e-4176c71dfa0b',  -- Aquifer Underground Services
   '168101f3-290b-4fad-9ebb-1ee074fde320',
   'submitted', NOW() - INTERVAL '3 days', NOW() - INTERVAL '2 days', NOW() - INTERVAL '1 day'),

  ('d000d000-0000-0000-0000-000000000103',
   'd000d000-0000-0000-0000-000000000002',
   '30199a0e-bb61-4c9a-b81b-a949f9998bc3',  -- Gateway Civil Partners
   'db025946-5ae0-4673-aadb-17337380f7ee',
   'submitted', NOW() - INTERVAL '3 days', NOW() - INTERVAL '2 days', NOW() - INTERVAL '6 hours'),

  -- ── 1 opened (vendor read the email but hasn't submitted yet) ──
  ('d000d000-0000-0000-0000-000000000104',
   'd000d000-0000-0000-0000-000000000002',
   'f8196f1f-52ee-4df7-8016-b65cb804bd82',  -- Heartland Survey Group
   '0b1ea214-f540-4c0f-a318-68f124b456c7',
   'opened', NOW() - INTERVAL '3 days', NOW() - INTERVAL '8 hours', NULL),

  -- ── 1 sent (vendor hasn't opened yet) ──
  ('d000d000-0000-0000-0000-000000000105',
   'd000d000-0000-0000-0000-000000000002',
   '7ad83f33-ba2c-4f2f-b2b4-b8cc22503ad6',  -- Meridian Land Consultants
   '62e09b4f-f670-41fe-8be9-f30f99b76b6c',
   'sent', NOW() - INTERVAL '2 days', NULL, NULL),

  -- ── 1 declined ──
  ('d000d000-0000-0000-0000-000000000106',
   'd000d000-0000-0000-0000-000000000002',
   '9c4da8c0-2f6e-4651-b8d2-d06336ff361c',  -- Prairie Point Engineers
   'd16f3dc5-8161-4dd7-8caa-aafc19aa5e4e',
   'declined', NOW() - INTERVAL '3 days', NOW() - INTERVAL '2 days', NOW() - INTERVAL '1 day'),

  -- ── 1 expired (sent before deadline, never responded) ──
  ('d000d000-0000-0000-0000-000000000107',
   'd000d000-0000-0000-0000-000000000002',
   '56be911e-84a7-4ba7-a413-dca2879e2dcd',  -- Ridgeline Engineering & Survey
   '59ddfa5d-b14c-43be-aac0-eb2e3d6bbfeb',
   'expired', NOW() - INTERVAL '5 days', NULL, NULL);


-- ── 4. 3 bid_submissions for the submitted invitations ───────────────────
--    Trigger fn_enforce_submission_vendor_consistency requires
--    bid_submissions.vendor_id == bid_invitations.vendor_id (we satisfy this).
--    Trigger fn_sync_bid_invitation_on_submission will fire on each insert
--    and (re)set the invitation's status='submitted', responded_at=NOW().
--
--    Amounts deliberately span the $50k budget: $41,200 (under), $47,500
--    (under), $52,800 (over) — exercises any future "bar above budget"
--    warning styling.

INSERT INTO bid_submissions (
  id, bid_invitation_id, vendor_id, total_amount,
  status, is_draft, is_direct_assign, submitted_at, vendor_notes
) VALUES
  ('d000d000-0000-0000-0000-000000000201',
   'd000d000-0000-0000-0000-000000000101',
   'ae788094-19b5-405f-aa0e-e71f6a7a5208',  -- AquaFlow
   41200.00, 'submitted', FALSE, FALSE, NOW() - INTERVAL '1 day',
   'Includes mobilization. Pricing held firm 30 days.'),

  ('d000d000-0000-0000-0000-000000000202',
   'd000d000-0000-0000-0000-000000000102',
   'dcb1bf07-dee8-4710-810e-4176c71dfa0b',  -- Aquifer
   47500.00, 'submitted', FALSE, FALSE, NOW() - INTERVAL '1 day',
   'Mobilization separate line. Schedule contingent on permitting.'),

  ('d000d000-0000-0000-0000-000000000203',
   'd000d000-0000-0000-0000-000000000103',
   '30199a0e-bb61-4c9a-b81b-a949f9998bc3',  -- Gateway
   52800.00, 'submitted', FALSE, FALSE, NOW() - INTERVAL '6 hours',
   'All-inclusive. Premium pricing reflects expedited start window.');


COMMIT;


-- ============================================================================
-- VERIFICATION (run after the seed completes — should all return 1 row each)
-- ============================================================================
--
-- SELECT id, name, status, budget_estimate
--   FROM tasks WHERE id = 'd000d000-0000-0000-0000-000000000001';
--
-- SELECT id, status, deadline, round_number
--   FROM bid_packages WHERE id = 'd000d000-0000-0000-0000-000000000002';
--
-- SELECT status, COUNT(*) FROM bid_invitations
--  WHERE bid_package_id = 'd000d000-0000-0000-0000-000000000002'
--  GROUP BY status ORDER BY status;
-- -- expected: submitted=3, opened=1, sent=1, declined=1, expired=1
--
-- SELECT bs.total_amount, v.company_name
--   FROM bid_submissions bs
--   JOIN vendors v ON v.id = bs.vendor_id
--  WHERE bs.bid_invitation_id IN (
--    SELECT id FROM bid_invitations
--     WHERE bid_package_id = 'd000d000-0000-0000-0000-000000000002'
--  )
--  ORDER BY bs.total_amount;
-- -- expected: 41200 AquaFlow, 47500 Aquifer, 52800 Gateway


-- ============================================================================
-- DEMO URL
-- ============================================================================
-- After seeding, navigate to:
--   /projects/3bb30c5d-1bc6-45eb-9ce9-a044b92bdb8b/tasks/d000d000-0000-0000-0000-000000000001/bid-packages/d000d000-0000-0000-0000-000000000002
-- (Or use the project → task → bid package navigation in the UI.)


-- ============================================================================
-- ⛏  CLEANUP — uncomment and run AFTER the demo
-- ============================================================================
-- This removes ONLY the demo rows under the d000d000-... namespace.
-- Pre-existing project, vendors, contacts, trades, templates, and your user
-- are untouched.
--
-- Order: child rows first (FKs are ON DELETE RESTRICT in most places).
--
-- BEGIN;
--
-- DELETE FROM bid_submissions
--  WHERE bid_invitation_id IN (
--    SELECT id FROM bid_invitations
--     WHERE bid_package_id = 'd000d000-0000-0000-0000-000000000002'
--  );
--
-- DELETE FROM bid_invitations
--  WHERE bid_package_id = 'd000d000-0000-0000-0000-000000000002';
--
-- DELETE FROM bid_packages
--  WHERE id = 'd000d000-0000-0000-0000-000000000002';
--
-- DELETE FROM tasks
--  WHERE id = 'd000d000-0000-0000-0000-000000000001';
--
-- COMMIT;
--
-- -- Verification (all should return 0):
-- -- SELECT COUNT(*) FROM tasks            WHERE id = 'd000d000-0000-0000-0000-000000000001';
-- -- SELECT COUNT(*) FROM bid_packages     WHERE id = 'd000d000-0000-0000-0000-000000000002';
-- -- SELECT COUNT(*) FROM bid_invitations  WHERE bid_package_id = 'd000d000-0000-0000-0000-000000000002';
-- -- SELECT COUNT(*) FROM bid_submissions  WHERE bid_invitation_id::text LIKE 'd000d000-0000-0000-0000-0000000001%';
