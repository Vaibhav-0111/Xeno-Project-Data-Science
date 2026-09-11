"""
validate_final.py
-----------------
Runs the final target_base SQL query against comm_log.db and validates
the result equals 22.  Also shows the per-family breakdown.
"""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "comm_log.db"
conn = sqlite3.connect(DB)

# ── FINAL TARGET BASE QUERY ─────────────────────────────────────────────
FINAL_SQL = """
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
        c.id  AS campaign_id,
        COALESCE(grandparent.id, parent.id, c.id) AS root_id
    FROM eligible c
    LEFT JOIN eligible parent      ON c.parent_id = parent.id
    LEFT JOIN eligible grandparent ON parent.parent_id = grandparent.id
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
        MAX(e.name) AS root_name,
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
SELECT SUM(contribution) AS target_base FROM per_family
"""

BREAKDOWN_SQL = """
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
    SELECT e.id FROM eligible e
    WHERE e.parent_id IS NULL
      AND NOT EXISTS (SELECT 1 FROM eligible ch WHERE ch.parent_id = e.id)
),
rooted AS (
    SELECT c.id AS campaign_id,
           COALESCE(gp.id, p.id, c.id) AS root_id
    FROM eligible c
    LEFT JOIN eligible p  ON c.parent_id = p.id
    LEFT JOIN eligible gp ON p.parent_id = gp.id
),
sends AS (
    SELECT r.root_id, cl.customer_id, cl.id AS log_id
    FROM communication_log cl
    JOIN rooted r ON cl.communication_id = r.campaign_id
    WHERE cl.merchant_id = 501
      AND strftime('%Y-%m', cl.sent_time) = '2026-10'
      AND cl.communication_type = '2'
),
per_family AS (
    SELECT s.root_id, MAX(e.name) AS root_name,
           CASE WHEN st.id IS NOT NULL THEN 'standalone' ELSE 'chain' END AS ftype,
           CASE WHEN st.id IS NOT NULL THEN COUNT(*) ELSE COUNT(DISTINCT s.customer_id) END AS contrib
    FROM sends s
    JOIN eligible e ON s.root_id = e.id
    LEFT JOIN standalone st ON s.root_id = st.id
    GROUP BY s.root_id, st.id
)
SELECT root_id, root_name, ftype AS family_type, contrib AS contribution FROM per_family
ORDER BY root_id
"""

print("=" * 65)
print("  FINAL VALIDATION: target_base for merchant 501, Oct 2026")
print("=" * 65)

# Per-family breakdown
print("\nPer-family breakdown:")
print(f"  {'root_id':<8} {'family_type':<12} {'contribution':>12}  root_name")
print("  " + "-"*62)
total = 0
for row in conn.execute(BREAKDOWN_SQL):
    root_id, root_name, ftype, contrib = row
    total += contrib
    print(f"  {root_id:<8} {ftype:<12} {contrib:>12}  {root_name}")
print("  " + "-"*62)
print(f"  {'TOTAL':<8} {'':<12} {total:>12}")

# Final scalar
result = conn.execute(FINAL_SQL).fetchone()[0]
print(f"\n  target_base = {result}")
print()
if result == 22:
    print("  [PASS] Matches Finance's expected value of 22.")
else:
    print(f"  [FAIL] Expected 22, got {result}.")

conn.close()
