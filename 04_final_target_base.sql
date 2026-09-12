-- =============================================================
-- 04_final_target_base.sql  (FINAL CORRECTED VERSION)
-- Purpose : Correct SQL returning target_base = 22
--           for merchant 501, October 2026, all Diwali campaigns.
-- Database: data/comm_log.db (SQLite)
-- Verified: Returns 22
-- =============================================================

-- ---------------------------------------------------------------
-- BUSINESS RULES (from README)
-- ---------------------------------------------------------------
-- 1. Eligible campaign:
--      creation_status  IN ('approved','aborted','resumed','stopped')
--      AND processing_status = 'processed'
-- 2. Retry chain family: campaigns linked via parent_id form a
--    "underlying communication". Target_base counts DISTINCT
--    customers across the whole chain.
-- 3. Standalone campaign: no parent_id AND no other campaign
--    points at it (no children). Each send row is its own event
--    ("every send under it is its own event" -- README line 74-75).
--    For standalones, COUNT(*) applies, not COUNT(DISTINCT customer_id).
-- ---------------------------------------------------------------

-- ---------------------------------------------------------------
-- STEP 0 — NAIVE QUERY  (result: 30)
-- ---------------------------------------------------------------
SELECT COUNT(*) AS naive_target_base  -- 30
FROM communication_log cl
JOIN campaign c ON cl.communication_id = c.id
WHERE cl.merchant_id = 501
  AND strftime('%Y-%m', cl.sent_time) = '2026-10'
  AND c.name LIKE '%Diwali%';

-- ---------------------------------------------------------------
-- STEP 1 — ELIGIBILITY FILTER  (30 -> 26, removes campaign 9004)
-- campaign 9004: creation_status = 'approval_awaiting' -> ineligible
-- ---------------------------------------------------------------
SELECT COUNT(*) AS after_eligibility  -- 26
FROM communication_log cl
JOIN campaign c ON cl.communication_id = c.id
WHERE cl.merchant_id = 501
  AND strftime('%Y-%m', cl.sent_time) = '2026-10'
  AND c.name LIKE '%Diwali%'
  AND c.creation_status IN ('approved','aborted','resumed','stopped')
  AND c.processing_status = 'processed';

-- ---------------------------------------------------------------
-- STEP 2-3 — CHAIN vs STANDALONE LOGIC  (26 -> 22)
--
-- Families in eligible Diwali campaigns:
--   Chain A : 9001 -> 9002 -> 9003  (10 distinct customers)
--   Standalone: 9101                (7 send events, C20 counted twice)
--   Chain B : 9201 -> 9202          (5 distinct customers)
--   Total: 10 + 7 + 5 = 22
-- ---------------------------------------------------------------

-- ---------------------------------------------------------------
-- FINAL QUERY — target_base = 22
-- ---------------------------------------------------------------
WITH

-- A: Eligible Diwali campaigns
eligible AS (
    SELECT id, parent_id, name
    FROM campaign
    WHERE merchant_id = 501
      AND name LIKE '%Diwali%'
      AND creation_status IN ('approved','aborted','resumed','stopped')
      AND processing_status = 'processed'
),

-- B: Identify standalone campaigns (no parent_id, no campaign points at them)
standalone AS (
    SELECT e.id
    FROM eligible e
    WHERE e.parent_id IS NULL                     -- no parent
      AND NOT EXISTS (                            -- no children either
          SELECT 1 FROM eligible child
          WHERE child.parent_id = e.id
      )
),

-- C: Assign each eligible campaign its root ancestor
--    (max chain depth in this dataset = 3 levels: 9001->9002->9003)
rooted AS (
    SELECT
        c.id   AS campaign_id,
        COALESCE(grandparent.id, parent.id, c.id) AS root_id
    FROM eligible c
    LEFT JOIN eligible parent
           ON c.parent_id = parent.id
    LEFT JOIN eligible grandparent
           ON parent.parent_id = grandparent.id
),

-- D: Qualifying send records, October 2026
sends AS (
    SELECT
        r.root_id,
        r.campaign_id,
        cl.customer_id,
        cl.id           AS log_id      -- needed for COUNT(*) of standalones
    FROM communication_log cl
    JOIN rooted r ON cl.communication_id = r.campaign_id
    WHERE cl.merchant_id        = 501
      AND strftime('%Y-%m', cl.sent_time) = '2026-10'
      AND cl.communication_type = '2'
),

-- E: Per-family contribution
--    Chain families  -> COUNT(DISTINCT customer_id)
--    Standalone      -> COUNT(*)  (each send event counts independently)
per_family AS (
    SELECT
        s.root_id,
        CASE
            WHEN st.id IS NOT NULL
            THEN COUNT(*)                         -- standalone: every send = 1 event
            ELSE COUNT(DISTINCT s.customer_id)    -- chain: distinct customers only
        END AS contribution
    FROM sends s
    LEFT JOIN standalone st ON s.root_id = st.id
    GROUP BY s.root_id, st.id
)

-- F: Sum = Finance target_base
SELECT SUM(contribution) AS target_base   -- 22
FROM per_family;


-- ---------------------------------------------------------------
-- VALIDATION — per-family breakdown
-- ---------------------------------------------------------------
WITH
eligible AS (
    SELECT id, parent_id, name
    FROM campaign
    WHERE merchant_id = 501
      AND name LIKE '%Diwali%'
      AND creation_status IN ('approved','aborted','resumed','stopped')
      AND processing_status = 'processed'
),
standalone AS (
    SELECT e.id
    FROM eligible e
    WHERE e.parent_id IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM eligible child WHERE child.parent_id = e.id
      )
),
rooted AS (
    SELECT
        c.id   AS campaign_id,
        COALESCE(grandparent.id, parent.id, c.id) AS root_id
    FROM eligible c
    LEFT JOIN eligible parent       ON c.parent_id = parent.id
    LEFT JOIN eligible grandparent  ON parent.parent_id = grandparent.id
),
sends AS (
    SELECT r.root_id, r.campaign_id, cl.customer_id, cl.id AS log_id
    FROM communication_log cl
    JOIN rooted r ON cl.communication_id = r.campaign_id
    WHERE cl.merchant_id = 501
      AND strftime('%Y-%m', cl.sent_time) = '2026-10'
      AND cl.communication_type = '2'
),
per_family AS (
    SELECT
        s.root_id,
        MAX(e.name)  AS root_name,
        CASE WHEN st.id IS NOT NULL THEN 'standalone' ELSE 'chain' END AS family_type,
        CASE
            WHEN st.id IS NOT NULL THEN COUNT(*)
            ELSE COUNT(DISTINCT s.customer_id)
        END AS contribution
    FROM sends s
    JOIN eligible e ON s.root_id = e.id
    LEFT JOIN standalone st ON s.root_id = st.id
    GROUP BY s.root_id, st.id
)
SELECT
    root_id,
    root_name,
    family_type,
    contribution,
    SUM(contribution) OVER () AS total_target_base
FROM per_family
ORDER BY root_id;
