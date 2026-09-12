-- =============================================================
-- 02_naive_count.sql
-- Purpose : Calculate the most obvious initial target_base count
--           before applying any data-quality adjustments.
-- Database: data/comm_log.db (SQLite)
-- =============================================================

-- Naive query: join communication_log to campaign on campaign id,
-- filter merchant 501, October 2026, Diwali campaigns,
-- count raw rows.
SELECT COUNT(*) AS naive_target_base
FROM communication_log cl
JOIN campaign c
    ON cl.communication_id = c.id
WHERE cl.merchant_id = 501
  AND strftime('%Y-%m', cl.sent_time) = '2026-10'
  AND c.name LIKE '%Diwali%';

-- Show the actual records included so we can see exactly what is counted
SELECT
    c.id           AS campaign_id,
    c.name         AS campaign_name,
    c.parent_id,
    c.creation_status,
    c.processing_status,
    cl.customer_id,
    cl.delivery_status,
    cl.sent_time
FROM communication_log cl
JOIN campaign c
    ON cl.communication_id = c.id
WHERE cl.merchant_id = 501
  AND strftime('%Y-%m', cl.sent_time) = '2026-10'
  AND c.name LIKE '%Diwali%'
ORDER BY c.id, cl.customer_id, cl.sent_time;

-- How many records per campaign?
SELECT
    c.id           AS campaign_id,
    c.name         AS campaign_name,
    c.creation_status,
    COUNT(*)       AS row_count
FROM communication_log cl
JOIN campaign c
    ON cl.communication_id = c.id
WHERE cl.merchant_id = 501
  AND strftime('%Y-%m', cl.sent_time) = '2026-10'
  AND c.name LIKE '%Diwali%'
GROUP BY c.id, c.name, c.creation_status
ORDER BY c.id;
