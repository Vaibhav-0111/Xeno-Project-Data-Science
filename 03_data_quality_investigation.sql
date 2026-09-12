-- =============================================================
-- 03_data_quality_investigation.sql
-- Purpose : Investigate all potential data-quality issues that
--           could explain the gap between the naive count and
--           Finance's target_base of 22.
-- Database: data/comm_log.db (SQLite)
-- =============================================================

-- ----------------------------------------------------------------
-- 3.1  Duplicate communication_log rows (exact duplicates)
-- ----------------------------------------------------------------
SELECT
    merchant_id, communication_id, customer_id,
    delivery_status, sent_time, scheduled_time,
    channel, credit_used,
    COUNT(*) AS row_count
FROM communication_log
GROUP BY merchant_id, communication_id, customer_id,
         delivery_status, sent_time, scheduled_time,
         channel, credit_used
HAVING COUNT(*) > 1;

-- ----------------------------------------------------------------
-- 3.2  Duplicate communication_log.id values
-- ----------------------------------------------------------------
SELECT id, COUNT(*) AS cnt
FROM communication_log
GROUP BY id
HAVING COUNT(*) > 1;

-- ----------------------------------------------------------------
-- 3.3  Multiple send events per (communication_id, customer_id)
-- ----------------------------------------------------------------
SELECT
    communication_id,
    customer_id,
    COUNT(*) AS events
FROM communication_log
WHERE merchant_id = 501
  AND strftime('%Y-%m', sent_time) = '2026-10'
GROUP BY communication_id, customer_id
HAVING COUNT(*) > 1;

-- 3.3b Specifically for Diwali campaigns
SELECT
    c.id     AS campaign_id,
    c.name   AS campaign_name,
    cl.customer_id,
    COUNT(*) AS events
FROM communication_log cl
JOIN campaign c ON cl.communication_id = c.id
WHERE cl.merchant_id = 501
  AND strftime('%Y-%m', cl.sent_time) = '2026-10'
  AND c.name LIKE '%Diwali%'
GROUP BY c.id, c.name, cl.customer_id
HAVING COUNT(*) > 1;

-- ----------------------------------------------------------------
-- 3.4  Ineligible campaigns — creation_status check
-- ----------------------------------------------------------------
-- The README states:
--   eligible = creation_status IN ('approved','aborted','resumed','stopped')
--              AND processing_status = 'processed'
-- 'approval_awaiting' is NOT in the eligible set.

SELECT
    c.id,
    c.name,
    c.creation_status,
    c.processing_status,
    COUNT(cl.id) AS log_rows
FROM campaign c
LEFT JOIN communication_log cl ON cl.communication_id = c.id
WHERE c.merchant_id = 501
  AND c.name LIKE '%Diwali%'
GROUP BY c.id, c.name, c.creation_status, c.processing_status
ORDER BY c.id;

-- Which campaigns are ineligible?
SELECT id, name, creation_status, processing_status
FROM campaign
WHERE merchant_id = 501
  AND name LIKE '%Diwali%'
  AND NOT (
      creation_status IN ('approved','aborted','resumed','stopped')
      AND processing_status = 'processed'
  );

-- ----------------------------------------------------------------
-- 3.5  Retry chain analysis — parent_id relationships
-- ----------------------------------------------------------------
-- Identify campaign families (root -> retries)
SELECT
    COALESCE(c.parent_id, c.id) AS root_id,
    c.id                        AS campaign_id,
    c.parent_id,
    c.name,
    c.creation_status,
    c.processing_status
FROM campaign c
WHERE c.merchant_id = 501
  AND c.name LIKE '%Diwali%'
ORDER BY root_id, c.id;

-- ----------------------------------------------------------------
-- 3.6  Target base logic per README:
--      For each ELIGIBLE campaign family (root + retries via parent_id),
--      count DISTINCT customers.
--      Standalone campaigns count distinct customers per campaign (same result).
--      Ineligible retry branches are excluded from both the chain count
--      and the distinct-customer deduplication.
-- ----------------------------------------------------------------

-- Step A: Identify eligible Diwali campaigns for merchant 501
SELECT
    id,
    parent_id,
    name,
    creation_status,
    processing_status
FROM campaign
WHERE merchant_id = 501
  AND name LIKE '%Diwali%'
  AND creation_status IN ('approved','aborted','resumed','stopped')
  AND processing_status = 'processed'
ORDER BY id;

-- Step B: For each eligible campaign, resolve the root campaign id
-- (walk up the parent_id chain to find the ancestor with parent_id IS NULL)
-- For this dataset, chains are max 2 levels deep, so one self-join suffices.
WITH eligible_campaigns AS (
    SELECT id, parent_id, name
    FROM campaign
    WHERE merchant_id = 501
      AND name LIKE '%Diwali%'
      AND creation_status IN ('approved','aborted','resumed','stopped')
      AND processing_status = 'processed'
),
rooted AS (
    SELECT
        c.id        AS campaign_id,
        COALESCE(grandparent.id, parent.id, c.id) AS root_id
    FROM eligible_campaigns c
    LEFT JOIN eligible_campaigns parent
        ON c.parent_id = parent.id
    LEFT JOIN eligible_campaigns grandparent
        ON parent.parent_id = grandparent.id
)
SELECT * FROM rooted ORDER BY root_id, campaign_id;

-- Step C: Count distinct customers per root family
WITH eligible_campaigns AS (
    SELECT id, parent_id, name
    FROM campaign
    WHERE merchant_id = 501
      AND name LIKE '%Diwali%'
      AND creation_status IN ('approved','aborted','resumed','stopped')
      AND processing_status = 'processed'
),
rooted AS (
    SELECT
        c.id        AS campaign_id,
        COALESCE(grandparent.id, parent.id, c.id) AS root_id
    FROM eligible_campaigns c
    LEFT JOIN eligible_campaigns parent
        ON c.parent_id = parent.id
    LEFT JOIN eligible_campaigns grandparent
        ON parent.parent_id = grandparent.id
),
sends AS (
    SELECT
        r.root_id,
        cl.customer_id
    FROM communication_log cl
    JOIN rooted r ON cl.communication_id = r.campaign_id
    WHERE cl.merchant_id = 501
      AND strftime('%Y-%m', cl.sent_time) = '2026-10'
)
SELECT
    root_id,
    COUNT(DISTINCT customer_id) AS distinct_customers
FROM sends
GROUP BY root_id
ORDER BY root_id;

-- Step D: Sum across families = target_base
WITH eligible_campaigns AS (
    SELECT id, parent_id, name
    FROM campaign
    WHERE merchant_id = 501
      AND name LIKE '%Diwali%'
      AND creation_status IN ('approved','aborted','resumed','stopped')
      AND processing_status = 'processed'
),
rooted AS (
    SELECT
        c.id        AS campaign_id,
        COALESCE(grandparent.id, parent.id, c.id) AS root_id
    FROM eligible_campaigns c
    LEFT JOIN eligible_campaigns parent
        ON c.parent_id = parent.id
    LEFT JOIN eligible_campaigns grandparent
        ON parent.parent_id = grandparent.id
),
sends AS (
    SELECT
        r.root_id,
        cl.customer_id
    FROM communication_log cl
    JOIN rooted r ON cl.communication_id = r.campaign_id
    WHERE cl.merchant_id = 501
      AND strftime('%Y-%m', cl.sent_time) = '2026-10'
),
per_family AS (
    SELECT
        root_id,
        COUNT(DISTINCT customer_id) AS distinct_customers
    FROM sends
    GROUP BY root_id
)
SELECT SUM(distinct_customers) AS target_base FROM per_family;

-- ----------------------------------------------------------------
-- 3.7  NULL checks
-- ----------------------------------------------------------------
SELECT
    COUNT(*) FILTER (WHERE communication_id IS NULL) AS null_comm_id,
    COUNT(*) FILTER (WHERE customer_id IS NULL)      AS null_customer,
    COUNT(*) FILTER (WHERE sent_time IS NULL)        AS null_sent_time,
    COUNT(*) FILTER (WHERE delivery_status IS NULL)  AS null_status
FROM communication_log;

-- ----------------------------------------------------------------
-- 3.8  JOIN validation — INNER vs LEFT JOIN difference
-- ----------------------------------------------------------------
SELECT COUNT(*) AS inner_join_count
FROM communication_log cl
JOIN campaign c ON cl.communication_id = c.id
WHERE cl.merchant_id = 501
  AND strftime('%Y-%m', cl.sent_time) = '2026-10';

SELECT COUNT(*) AS left_join_count
FROM communication_log cl
LEFT JOIN campaign c ON cl.communication_id = c.id
WHERE cl.merchant_id = 501
  AND strftime('%Y-%m', cl.sent_time) = '2026-10';

-- ----------------------------------------------------------------
-- 3.9  Duplicate campaign.id check
-- ----------------------------------------------------------------
SELECT id, COUNT(*) AS cnt
FROM campaign
GROUP BY id
HAVING COUNT(*) > 1;

-- ----------------------------------------------------------------
-- 3.10  Campaign name variations / case sensitivity
-- ----------------------------------------------------------------
SELECT DISTINCT name FROM campaign WHERE merchant_id = 501 ORDER BY name;
