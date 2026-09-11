-- =============================================================
-- 01_schema_exploration.sql
-- Purpose : Inspect database structure, table schemas, and
--           overall data profile for the comm-log assignment.
-- Database: comm_log.db (SQLite)
-- Author  : Data Analyst Candidate
-- =============================================================

-- 1. List all tables
SELECT name AS table_name
FROM sqlite_master
WHERE type = 'table'
ORDER BY name;

-- 2. Schema of campaign table
PRAGMA table_info(campaign);

-- 3. Schema of communication_log table
PRAGMA table_info(communication_log);

-- 4. Overall data profile
SELECT
    'campaign'           AS table_name,
    COUNT(*)             AS total_rows,
    COUNT(DISTINCT id)   AS distinct_ids
FROM campaign
UNION ALL
SELECT
    'communication_log',
    COUNT(*),
    COUNT(DISTINCT id)
FROM communication_log;

-- 5. Campaign table — full inspection
SELECT
    id,
    merchant_id,
    parent_id,
    name,
    creation_status,
    processing_status
FROM campaign
ORDER BY id;

-- 6. Distinct values in categorical columns
SELECT DISTINCT creation_status  FROM campaign ORDER BY 1;
SELECT DISTINCT processing_status FROM campaign ORDER BY 1;

-- 7. communication_log — date range and distinct values
SELECT
    MIN(sent_time)                    AS earliest_sent,
    MAX(sent_time)                    AS latest_sent,
    COUNT(*)                          AS total_rows,
    COUNT(DISTINCT merchant_id)       AS distinct_merchants,
    COUNT(DISTINCT communication_id)  AS distinct_campaigns,
    COUNT(DISTINCT customer_id)       AS distinct_customers
FROM communication_log;

SELECT DISTINCT delivery_status    FROM communication_log ORDER BY 1;
SELECT DISTINCT communication_type FROM communication_log ORDER BY 1;
SELECT DISTINCT channel            FROM communication_log ORDER BY 1;
