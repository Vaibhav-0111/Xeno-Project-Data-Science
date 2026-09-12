# Data Analyst Take-Home Assignment

## Comm-Log Send Reconciliation

---

### 1. Executive Summary

**Business question:** For merchant **501**, during **October 2026**, across all Diwali campaigns, reproduce Finance's `target_base` of **22** from the raw communication data and explain every gap between the naive count and the final number.

| Metric | Value |
|---|---|
| Naive row count (no adjustments) | **30** |
| Ineligible rows removed (campaign 9004) | **−4** |
| Rows deduplicated inside retry chains | **−4** (C2 ×2, C3 ×3, D1 ×1 cross-campaign) |
| Standalone send events retained (C20 ×2) | counted as **+0** (already in raw count) |
| **Finance target\_base** | **22** |

Three adjustments are required:

1. **Eligibility gate** — campaign 9004 (`approval_awaiting`) is not approved for reporting; its 4 rows are excluded.
2. **Retry-chain deduplication** — within a campaign family linked by `parent_id`, a customer who appears across multiple retry campaigns counts only once.
3. **Standalone semantics** — campaign 9101 has no parent and no children, making it a *standalone* communication. The README explicitly states that "every send under it is its own event, whether or not the same customer appears twice." Customer C20's two sends under 9101 therefore count as **2**, not 1.

**Conclusion:** `target_base = 10 (Family A) + 7 (9101 standalone) + 5 (Family B) = 22` ✓

---

### 2. Data Understanding

#### 2.1 Files inspected

| File | Contents |
|---|---|
| `README.md` | Data dictionary, business rules, retry-chain semantics, scope |
| `data/comm_log.db` | SQLite database with tables `campaign` and `communication_log` |
| `data/campaign.csv` | CSV mirror of the `campaign` table (7 rows) |
| `data/communication_log.csv` | CSV mirror of `communication_log` table (30 rows) |

#### 2.2 Table: `campaign` (7 rows)

| Column | Type | Meaning |
|---|---|---|
| `id` | int PK | Campaign identifier |
| `merchant_id` | int | Owning merchant |
| `parent_id` | int, nullable | If set, this campaign is a retry of `parent_id` |
| `name` | text | Human-readable campaign label |
| `creation_status` | text | Approval workflow state |
| `processing_status` | text | Send-pipeline state |

**Eligibility rule** *(verified from README)*:

```
creation_status IN ('approved', 'aborted', 'resumed', 'stopped')
AND processing_status = 'processed'
```

#### 2.3 Table: `communication_log` (30 rows)

| Column | Type | Meaning |
|---|---|---|
| `id` | int PK | Row identifier (one per send attempt) |
| `merchant_id` | int | Owning merchant |
| `communication_id` | int FK | References `campaign.id` |
| `customer_id` | text | Customer targeted |
| `communication_type` | text | `'2'` = Campaign (only value in dataset) |
| `delivery_status` | int | `900` = delivered; `1100` = failed |
| `sent_time` / `scheduled_time` | timestamp | When the send happened |
| `credit_used` | int | Billing credits |
| `channel` | text | `sms` throughout |

#### 2.4 Data model and relationships

```
campaign.id  <---  communication_log.communication_id
              (one campaign : many log rows)

campaign.parent_id  --->  campaign.id
              (retry chain: child -> parent -> grandparent -> root)
```

#### 2.5 Campaign inventory

| id | parent_id | name | creation_status | Eligibility | Role |
|---|---|---|---|---|---|
| 9001 | — | Diwali Cart Recovery - Wave 1 | approved | **ELIGIBLE** | Chain root (Family A) |
| 9002 | 9001 | Diwali Cart Recovery - Retry A | approved | **ELIGIBLE** | Chain member (Family A) |
| 9003 | 9002 | Diwali Cart Recovery - Retry B | approved | **ELIGIBLE** | Chain member (Family A) |
| 9004 | 9001 | Diwali Cart Recovery - Retry C (pending) | **approval_awaiting** | **INELIGIBLE** | Excluded |
| 9101 | — | Diwali Flash Sale - Standalone | approved | **ELIGIBLE** | Standalone |
| 9201 | — | Diwali Wave 2 | approved | **ELIGIBLE** | Chain root (Family B) |
| 9202 | 9201 | Diwali Wave 2 - Retry | approved | **ELIGIBLE** | Chain member (Family B) |

---

### 3. Investigation Methodology

1. **Read the README** — extracted eligibility rules, retry-chain definition, and standalone semantics before writing any SQL.
2. **Inspected all raw data** — confirmed schema via `PRAGMA table_info`, read every row in both tables.
3. **Calculated the naive count** — `JOIN + COUNT(*)` with merchant/date/Diwali filters → **30**.
4. **Investigated data quality issues:**
   - Exact duplicate rows → **None**
   - Duplicate `campaign.id` → **None**
   - Missing JOIN matches → **None** (INNER = LEFT JOIN = 30)
   - NULL values → **None** in any relevant column
   - Delivery_status filter needed → **No** (README does not restrict by delivery status)
   - Date-range issues → **No** (all records within October 2026)
   - Campaign name variations → **No** (all match `LIKE '%Diwali%'`)
5. **Applied eligibility filter** → campaign 9004 excluded → **26**.
6. **Resolved retry chains** — walked `parent_id` to identify three families.
7. **Applied chain vs standalone counting rules** → **22**.
8. **Validated** — `validate_final.py` confirmed **22** against live SQLite database.

---

### 4. Naive Count

```sql
SELECT COUNT(*) AS naive_target_base
FROM communication_log cl
JOIN campaign c ON cl.communication_id = c.id
WHERE cl.merchant_id = 501
  AND strftime('%Y-%m', cl.sent_time) = '2026-10'
  AND c.name LIKE '%Diwali%';
```

**Result: 30**

| campaign_id | name | creation_status | rows |
|---|---|---|---|
| 9001 | Diwali Cart Recovery - Wave 1 | approved | 10 |
| 9002 | Diwali Cart Recovery - Retry A | approved | 2 |
| 9003 | Diwali Cart Recovery - Retry B | approved | 1 |
| **9004** | **Diwali Cart Recovery - Retry C (pending)** | **approval_awaiting** | **4** |
| 9101 | Diwali Flash Sale - Standalone | approved | 7 |
| 9201 | Diwali Wave 2 | approved | 5 |
| 9202 | Diwali Wave 2 - Retry | approved | 1 |
| **Total** | | | **30** |

---

### 5. Reconciliation Bridge

| Step | Description | Running total | Reason |
|---|---|---:|---|
| **0** | Naive row count | **30** | All communication_log rows joined to Diwali campaigns, merchant 501, Oct 2026 |
| **1** | Remove ineligible campaign 9004 (−4 rows) | **26** | `creation_status = 'approval_awaiting'` — not in approved set |
| **2a** | Apply Family A chain dedup (C2 ×2, C3 ×3 = 13 rows → 10 distinct) | **23** | C2 and C3 each span multiple campaigns in chain 9001→9002→9003 |
| **2b** | Apply Family B chain dedup (D1 ×2 → 1 distinct) | **22** | D1 appears in both 9201 and 9202 |
| **3** | Standalone 9101 uses COUNT(*) not COUNT(DISTINCT) — C20 ×2 counted correctly | **22** | README: "every send under [a standalone] is its own event" |
| **Final** | **Finance target_base** | **22** | Reconciled ✓ |

**Per-family verification:**

| Root ID | Family name | Type | Contribution |
|---|---|---|---:|
| 9001 | Diwali Cart Recovery (Wave 1 + Retry A + Retry B) | Chain | **10** |
| 9101 | Diwali Flash Sale - Standalone | Standalone | **7** |
| 9201 | Diwali Wave 2 (+ Retry) | Chain | **5** |
| | **target_base** | | **22** |

---

### 6. Detailed Findings and Adjustments

#### Finding 1 — Ineligible campaign 9004 (−4 rows)

Campaign 9004 has `creation_status = 'approval_awaiting'`. The README states: *"A campaign still `approval_awaiting` has not been signed off and does not count toward reported sends, even if `communication_log` rows already exist for it."* Four send rows (customers C11–C14) are removed.

#### Finding 2 — Retry-chain deduplication (net −4 cross-campaign rows)

- **C2**: appears in campaigns 9001 (failed) and 9002 (delivered) → 2 rows, 1 customer.
- **C3**: appears in campaigns 9001 (failed), 9002 (failed), 9003 (delivered) → 3 rows, 1 customer.
- **D1**: appears in campaigns 9201 (failed) and 9202 (delivered) → 2 rows, 1 customer.

Total: 4 redundant cross-campaign rows removed within chains.

#### Finding 3 — Standalone campaign C20 double-send (critical insight)

Campaign 9101 has `parent_id IS NULL` and no other campaign points to it → pure standalone. The README says standalone campaigns count "every send as its own event." C20 was sent on 2026-10-10 and again on 2026-10-20 — two independent business events. Both count. Applying `COUNT(DISTINCT customer_id)` to 9101 gives 6; applying `COUNT(*)` gives 7. The correct answer is 7.

#### Finding 4 — No other data quality issues (documented, non-impacting)

| Check | Result |
|---|---|
| Exact duplicate rows | None |
| Duplicate communication_log.id | None |
| Duplicate campaign.id | None |
| NULL values in key columns | None |
| INNER vs LEFT JOIN difference | None (both = 30) |
| Date boundary issues | None (all records in Oct 2026) |
| Delivery_status filter needed | Not applicable per README |

---

### 7. Final SQL Query

```sql
-- =============================================================
-- Final target_base SQL
-- Database: comm_log.db (SQLite)  |  Returns: 22
-- =============================================================
WITH

-- Step A: Eligible Diwali campaigns for merchant 501
eligible AS (
    SELECT id, parent_id, name
    FROM campaign
    WHERE merchant_id = 501
      AND name LIKE '%Diwali%'
      AND creation_status IN ('approved','aborted','resumed','stopped')
      AND processing_status = 'processed'
),

-- Step B: Identify pure standalone campaigns
--         (no parent AND no other campaign points at them)
standalone AS (
    SELECT e.id
    FROM eligible e
    WHERE e.parent_id IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM eligible child WHERE child.parent_id = e.id
      )
),

-- Step C: Resolve root ancestor for each eligible campaign
--         (max chain depth = 3: 9001->9002->9003)
rooted AS (
    SELECT
        c.id  AS campaign_id,
        COALESCE(grandparent.id, parent.id, c.id) AS root_id
    FROM eligible c
    LEFT JOIN eligible parent      ON c.parent_id = parent.id
    LEFT JOIN eligible grandparent ON parent.parent_id = grandparent.id
),

-- Step D: Qualifying send records, October 2026
sends AS (
    SELECT r.root_id, cl.customer_id, cl.id AS log_id
    FROM communication_log cl
    JOIN rooted r ON cl.communication_id = r.campaign_id
    WHERE cl.merchant_id        = 501
      AND strftime('%Y-%m', cl.sent_time) = '2026-10'
      AND cl.communication_type = '2'
),

-- Step E: Per-family contribution
--   Retry chains  -> COUNT(DISTINCT customer_id)
--   Standalone    -> COUNT(*)  (each send is an independent event)
per_family AS (
    SELECT
        s.root_id,
        CASE
            WHEN st.id IS NOT NULL
            THEN COUNT(*)
            ELSE COUNT(DISTINCT s.customer_id)
        END AS contribution
    FROM sends s
    LEFT JOIN standalone st ON s.root_id = st.id
    GROUP BY s.root_id, st.id
)

-- Final: sum contributions across all families
SELECT SUM(contribution) AS target_base   -- 22
FROM per_family;
```

---

### 8. Validation

**Command executed:** `python validate_final.py`

**Output:**

```
=================================================================
  FINAL VALIDATION: target_base for merchant 501, Oct 2026
=================================================================

Per-family breakdown:
  root_id  family_type  contribution  root_name
  --------------------------------------------------------------
  9001     chain                  10  Diwali Cart Recovery - Wave 1
  9101     standalone              7  Diwali Flash Sale - Standalone
  9201     chain                   5  Diwali Wave 2
  --------------------------------------------------------------
  TOTAL                           22

  target_base = 22

  [PASS] Matches Finance's expected value of 22.
```

| Validation check | Status |
|---|---|
| Query runs without errors | PASS |
| Result is exactly 22 | PASS |
| Correct merchant (501) | PASS |
| Correct month (Oct 2026) | PASS |
| All 6 eligible Diwali campaigns included | PASS |
| Ineligible campaign 9004 excluded | PASS |
| Chain dedup applied (C2, C3, D1) | PASS |
| Standalone C20 ×2 counted | PASS |
| No JOIN multiplication | PASS |
| No unmatched communication_log rows | PASS |

---

### 9. Data Surprises

The most surprising finding was the **dual counting rule for standalone versus chained campaigns**. A naïve analyst querying this dataset would almost certainly apply `COUNT(DISTINCT customer_id)` across all campaign families — a reasonable assumption that gives **21**, not 22. The README contains the critical clarification only in lines 73–75: *"A campaign with no retry chain at all … is a standalone communication — every send under it is its own event, whether or not the same customer appears twice."* Campaign 9101 ("Diwali Flash Sale - Standalone") is the only campaign in the dataset meeting this exact definition, and customer C20 was genuinely re-targeted under it on 2026-10-10 and again on 2026-10-20 — two independent business events, not a data error. Getting to 22 requires recognising this distinction before writing the final SQL.

A secondary surprise was **campaign 9004** ("Diwali Cart Recovery - Retry C (pending)"). It is structurally a retry of campaign 9001, its 4 communication_log rows already exist with delivery_status = 900 (successfully delivered), yet it is entirely excluded from `target_base` because its `creation_status` is `approval_awaiting`. The README explains that the send pipeline can run ahead of the approval workflow, meaning send-log data for unapproved campaigns is real but unreportable. Any analyst counting sends without checking `creation_status` will over-count by 4. Together, these two issues account for the entire 8-unit gap between the naive count of 30 and Finance's verified `target_base` of 22.

---

### 10. Final Conclusion

`target_base` is Finance's metric for counting how many customers were reached by a given underlying communication during a reporting period. For merchant 501 in October 2026 across all Diwali campaigns, the correct value is **22**.

The naive count of 30 differs from 22 for two root causes:

1. **Eligibility** — campaign 9004 is in `approval_awaiting` status. Its 4 send records exist in the database but have not cleared the approval gate. Excluding them reduces the count from 30 to 26.

2. **Business-rule aggregation** — the remaining 26 rows belong to three distinct underlying communications, each aggregated differently:
   - **Family A (9001→9002→9003):** 13 raw rows → **10 distinct customers**.
   - **Standalone 9101:** 7 raw rows → **7 send events** (README: every send is its own event).
   - **Family B (9201→9202):** 6 raw rows → **5 distinct customers**.
   - Total: 10 + 7 + 5 = **22**.

All findings are evidence-based, supported by SQL queries executed against `data/comm_log.db`, and validated independently by `validate_final.py`.

---

### 11. Submission Readiness Checklist

- [x] All uploaded files inspected
- [x] README and schema fully understood before any SQL was written
- [x] Actual naive count calculated from live data: **30**
- [x] All relevant adjustments investigated with evidence
- [x] Every adjustment supported by a SQL query and README reference
- [x] Reconciliation bridge ends at **22**
- [x] Final SQL is executable against SQLite (`data/comm_log.db`)
- [x] SQL result independently validated (`validate_final.py`)
- [x] Data surprises paragraph included
- [x] No fabricated data or assumptions presented as facts
- [x] Final submission is professionally formatted and auditable
