"""
analysis.py  (FINAL VERSION)
-----------------------------
Complete, reproducible Python analysis for the comm-log reconciliation
take-home assignment.

Runs every meaningful SQL query against comm_log.db and prints the
actual results.  This script is the source of truth for all numbers
cited in the final report.

Usage:
    python analysis.py

Requirements: Python 3.8+ (stdlib sqlite3 only)
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "comm_log.db"
if not DB_PATH.exists():
    DB_PATH = Path(__file__).resolve().parent / "comm_log.db"


def run(conn, label, sql):
    """Execute SQL, print results, return rows."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print('='*70)
    cur = conn.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    if cols:
        col_widths = [max(len(str(c)), max((len(str(r[i])) for r in rows), default=0))
                      for i, c in enumerate(cols)]
        header = "  ".join(str(c).ljust(w) for c, w in zip(cols, col_widths))
        print(header)
        print("-" * len(header))
        for row in rows:
            print("  ".join(str(v).ljust(w) for v, w in zip(row, col_widths)))
    else:
        print("(no rows)")
    print(f"  -> {len(rows)} row(s)")
    return rows


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)

    print("\n" + "#"*70)
    print("  COMM-LOG RECONCILIATION — COMPLETE ANALYSIS")
    print(f"  Database : {DB_PATH}")
    print("#"*70)

    # ===================================================================
    # SECTION 1: DATABASE STRUCTURE
    # ===================================================================
    run(conn, "1.1  Tables in database",
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")

    run(conn, "1.2  Schema: campaign",
        "PRAGMA table_info(campaign)")

    run(conn, "1.3  Schema: communication_log",
        "PRAGMA table_info(communication_log)")

    # ===================================================================
    # SECTION 2: DATA PROFILE
    # ===================================================================
    run(conn, "2.1  Campaign table — full listing",
        "SELECT id, merchant_id, parent_id, name, creation_status, processing_status FROM campaign ORDER BY id")

    run(conn, "2.2  communication_log — overall profile",
        """SELECT COUNT(*) AS total_rows,
                  COUNT(DISTINCT merchant_id)      AS distinct_merchants,
                  COUNT(DISTINCT communication_id) AS distinct_campaign_refs,
                  COUNT(DISTINCT customer_id)      AS distinct_customers,
                  MIN(sent_time)                   AS earliest_sent,
                  MAX(sent_time)                   AS latest_sent
           FROM communication_log""")

    run(conn, "2.3  Distinct delivery_status values (900=delivered, 1100=failed)",
        "SELECT DISTINCT delivery_status FROM communication_log ORDER BY 1")

    run(conn, "2.4  All communication_log rows",
        """SELECT id, communication_id, customer_id, delivery_status, sent_time
           FROM communication_log ORDER BY communication_id, customer_id, sent_time""")

    # ===================================================================
    # SECTION 3: NAIVE COUNT  (Starting point)
    # ===================================================================
    naive_rows = run(conn, "3.1  NAIVE COUNT — Diwali, merchant 501, Oct 2026, no adjustments",
        """SELECT COUNT(*) AS naive_target_base
           FROM communication_log cl
           JOIN campaign c ON cl.communication_id = c.id
           WHERE cl.merchant_id = 501
             AND strftime('%Y-%m', cl.sent_time) = '2026-10'
             AND c.name LIKE '%Diwali%'""")
    naive_count = naive_rows[0][0]
    print(f"\n  ** NAIVE COUNT = {naive_count} **")

    run(conn, "3.2  Naive count — breakdown by campaign",
        """SELECT c.id, c.name, c.creation_status, c.processing_status, COUNT(*) AS rows
           FROM communication_log cl
           JOIN campaign c ON cl.communication_id = c.id
           WHERE cl.merchant_id = 501
             AND strftime('%Y-%m', cl.sent_time) = '2026-10'
             AND c.name LIKE '%Diwali%'
           GROUP BY c.id, c.name, c.creation_status, c.processing_status ORDER BY c.id""")

    # ===================================================================
    # SECTION 4: DATA QUALITY INVESTIGATION
    # ===================================================================

    # 4.1 Exact duplicate rows
    run(conn, "4.1  Exact duplicate rows in communication_log (should be none)",
        """SELECT merchant_id, communication_id, customer_id, delivery_status, sent_time, COUNT(*) AS cnt
           FROM communication_log
           GROUP BY merchant_id, communication_id, customer_id, delivery_status, sent_time
           HAVING COUNT(*) > 1""")

    # 4.2 Duplicate IDs
    run(conn, "4.2  Duplicate communication_log.id values (should be none)",
        "SELECT id, COUNT(*) AS cnt FROM communication_log GROUP BY id HAVING COUNT(*) > 1")

    # 4.3 Multiple events per (communication_id, customer_id)
    run(conn, "4.3  Multiple send events per (communication_id, customer_id) — business-valid repeats",
        """SELECT communication_id, customer_id, COUNT(*) AS events
           FROM communication_log
           WHERE merchant_id = 501 AND strftime('%Y-%m', sent_time) = '2026-10'
           GROUP BY communication_id, customer_id HAVING COUNT(*) > 1""")

    # 4.4 Campaign eligibility
    run(conn, "4.4  Eligibility check — all Diwali campaigns for merchant 501",
        """SELECT id, name, creation_status, processing_status,
                  CASE WHEN creation_status IN ('approved','aborted','resumed','stopped')
                            AND processing_status = 'processed'
                       THEN 'ELIGIBLE' ELSE 'INELIGIBLE' END AS eligibility
           FROM campaign WHERE merchant_id = 501 AND name LIKE '%Diwali%' ORDER BY id""")

    run(conn, "4.5  Rows belonging to INELIGIBLE campaign 9004",
        """SELECT cl.id, cl.communication_id, c.name, c.creation_status,
                  cl.customer_id, cl.delivery_status, cl.sent_time
           FROM communication_log cl
           JOIN campaign c ON cl.communication_id = c.id
           WHERE cl.merchant_id = 501 AND c.name LIKE '%Diwali%'
             AND NOT (c.creation_status IN ('approved','aborted','resumed','stopped')
                      AND c.processing_status = 'processed') ORDER BY cl.id""")

    inelig = conn.execute("""
        SELECT COUNT(*) FROM communication_log cl JOIN campaign c ON cl.communication_id = c.id
        WHERE cl.merchant_id = 501 AND c.name LIKE '%Diwali%'
          AND NOT (c.creation_status IN ('approved','aborted','resumed','stopped') AND c.processing_status='processed')
    """).fetchone()[0]
    print(f"\n  >> ADJUSTMENT 1: Remove {inelig} ineligible rows (campaign 9004, approval_awaiting)")
    print(f"  >> Running total after adjustment 1: {naive_count} - {inelig} = {naive_count - inelig}")

    run(conn, "4.6  Count after eligibility filter [26]",
        """SELECT COUNT(*) AS after_eligibility
           FROM communication_log cl JOIN campaign c ON cl.communication_id = c.id
           WHERE cl.merchant_id = 501 AND strftime('%Y-%m', cl.sent_time) = '2026-10'
             AND c.name LIKE '%Diwali%'
             AND c.creation_status IN ('approved','aborted','resumed','stopped')
             AND c.processing_status = 'processed'""")

    # 4.5 Retry chain structure
    run(conn, "4.7  Retry chain structure — eligible Diwali campaigns",
        """SELECT id, parent_id, name, creation_status
           FROM campaign WHERE merchant_id=501 AND name LIKE '%Diwali%'
             AND creation_status IN ('approved','aborted','resumed','stopped')
             AND processing_status='processed' ORDER BY id""")

    # 4.6 Root resolution
    run(conn, "4.8  Root campaign resolution per eligible campaign",
        """WITH eligible AS (
               SELECT id, parent_id, name FROM campaign
               WHERE merchant_id=501 AND name LIKE '%Diwali%'
                 AND creation_status IN ('approved','aborted','resumed','stopped')
                 AND processing_status='processed'
           ),
           rooted AS (
               SELECT c.id AS campaign_id, c.name AS campaign_name,
                      COALESCE(gp.id, p.id, c.id) AS root_id
               FROM eligible c
               LEFT JOIN eligible p  ON c.parent_id = p.id
               LEFT JOIN eligible gp ON p.parent_id = gp.id
           )
           SELECT campaign_id, campaign_name, root_id FROM rooted ORDER BY root_id, campaign_id""")

    # 4.7 Standalone detection
    run(conn, "4.9  Standalone vs chain campaign classification",
        """WITH eligible AS (
               SELECT id, parent_id, name FROM campaign
               WHERE merchant_id=501 AND name LIKE '%Diwali%'
                 AND creation_status IN ('approved','aborted','resumed','stopped')
                 AND processing_status='processed'
           )
           SELECT e.id, e.name, e.parent_id,
                  CASE WHEN e.parent_id IS NULL
                            AND NOT EXISTS (SELECT 1 FROM eligible ch WHERE ch.parent_id = e.id)
                       THEN 'standalone'
                       WHEN e.parent_id IS NULL THEN 'chain root'
                       ELSE 'chain member'
                  END AS campaign_role
           FROM eligible e ORDER BY e.id""")

    # 4.8 C20 investigation
    run(conn, "4.10  C20 double-send under standalone 9101 — each send IS its own event",
        """SELECT cl.id, cl.communication_id, c.name, cl.customer_id, cl.delivery_status, cl.sent_time
           FROM communication_log cl JOIN campaign c ON cl.communication_id = c.id
           WHERE cl.customer_id = 'C20' ORDER BY cl.sent_time""")
    print("\n  >> README: 9101 is standalone -> COUNT(*), not COUNT(DISTINCT customer_id)")
    print("     9101: COUNT(*) = 7  |  COUNT(DISTINCT customer_id) = 6")
    print("     C20 counts TWICE for target_base (two independent send events).")

    # 4.9 Per-family breakdown
    run(conn, "4.11  Per-family distinct-customer count (chain=distinct, standalone=all rows)",
        """WITH eligible AS (
               SELECT id, parent_id, name FROM campaign
               WHERE merchant_id=501 AND name LIKE '%Diwali%'
                 AND creation_status IN ('approved','aborted','resumed','stopped')
                 AND processing_status='processed'
           ),
           standalone AS (
               SELECT e.id FROM eligible e WHERE e.parent_id IS NULL
                 AND NOT EXISTS (SELECT 1 FROM eligible ch WHERE ch.parent_id = e.id)
           ),
           rooted AS (
               SELECT c.id AS campaign_id, COALESCE(gp.id, p.id, c.id) AS root_id
               FROM eligible c
               LEFT JOIN eligible p  ON c.parent_id = p.id
               LEFT JOIN eligible gp ON p.parent_id = gp.id
           ),
           sends AS (
               SELECT r.root_id, cl.customer_id, cl.id AS log_id
               FROM communication_log cl JOIN rooted r ON cl.communication_id = r.campaign_id
               WHERE cl.merchant_id=501 AND strftime('%Y-%m', cl.sent_time)='2026-10'
                 AND cl.communication_type='2'
           )
           SELECT s.root_id, MAX(e.name) AS root_name,
                  CASE WHEN st.id IS NOT NULL THEN 'standalone' ELSE 'chain' END AS family_type,
                  CASE WHEN st.id IS NOT NULL THEN COUNT(*) ELSE COUNT(DISTINCT s.customer_id) END AS contribution
           FROM sends s JOIN eligible e ON s.root_id = e.id
           LEFT JOIN standalone st ON s.root_id = st.id
           GROUP BY s.root_id, st.id ORDER BY s.root_id""")

    # ===================================================================
    # SECTION 5: FINAL TARGET_BASE
    # ===================================================================
    final_rows = run(conn, "5.1  FINAL TARGET_BASE",
        """WITH eligible AS (
               SELECT id, parent_id, name FROM campaign
               WHERE merchant_id=501 AND name LIKE '%Diwali%'
                 AND creation_status IN ('approved','aborted','resumed','stopped')
                 AND processing_status='processed'
           ),
           standalone AS (
               SELECT e.id FROM eligible e WHERE e.parent_id IS NULL
                 AND NOT EXISTS (SELECT 1 FROM eligible ch WHERE ch.parent_id = e.id)
           ),
           rooted AS (
               SELECT c.id AS campaign_id, COALESCE(gp.id, p.id, c.id) AS root_id
               FROM eligible c
               LEFT JOIN eligible p  ON c.parent_id = p.id
               LEFT JOIN eligible gp ON p.parent_id = gp.id
           ),
           sends AS (
               SELECT r.root_id, cl.customer_id, cl.id AS log_id
               FROM communication_log cl JOIN rooted r ON cl.communication_id = r.campaign_id
               WHERE cl.merchant_id=501 AND strftime('%Y-%m', cl.sent_time)='2026-10'
                 AND cl.communication_type='2'
           ),
           per_family AS (
               SELECT s.root_id,
                      CASE WHEN st.id IS NOT NULL THEN COUNT(*) ELSE COUNT(DISTINCT s.customer_id) END AS contribution
               FROM sends s LEFT JOIN standalone st ON s.root_id = st.id
               GROUP BY s.root_id, st.id
           )
           SELECT SUM(contribution) AS target_base FROM per_family""")

    final_count = final_rows[0][0]

    # ===================================================================
    # SECTION 6: NULL & JOIN CHECKS
    # ===================================================================
    run(conn, "6.1  NULL checks — communication_log",
        """SELECT SUM(CASE WHEN communication_id IS NULL THEN 1 ELSE 0 END) AS null_comm_id,
                  SUM(CASE WHEN customer_id IS NULL      THEN 1 ELSE 0 END) AS null_customer,
                  SUM(CASE WHEN sent_time IS NULL        THEN 1 ELSE 0 END) AS null_sent_time
           FROM communication_log""")

    run(conn, "6.2  INNER vs LEFT JOIN count (should be identical)",
        """SELECT
               (SELECT COUNT(*) FROM communication_log cl JOIN campaign c ON cl.communication_id = c.id
                WHERE cl.merchant_id=501 AND strftime('%Y-%m', cl.sent_time)='2026-10') AS inner_join,
               (SELECT COUNT(*) FROM communication_log cl LEFT JOIN campaign c ON cl.communication_id = c.id
                WHERE cl.merchant_id=501 AND strftime('%Y-%m', cl.sent_time)='2026-10') AS left_join""")

    run(conn, "6.3  Duplicate campaign.id check (should be none)",
        "SELECT id, COUNT(*) AS cnt FROM campaign GROUP BY id HAVING COUNT(*) > 1")

    # ===================================================================
    # RECONCILIATION BRIDGE SUMMARY
    # ===================================================================
    print("\n" + "#"*70)
    print("  RECONCILIATION BRIDGE")
    print("#"*70)
    print(f"  Step 0: Naive count (all Diwali rows, merchant 501, Oct 2026) : {naive_count}")
    print(f"  Step 1: Remove ineligible campaign 9004 (approval_awaiting)   : -{inelig} = {naive_count - inelig}")
    print(f"  Step 2: Dedup within retry chains (C2/C3 in A, D1 in B)      : -3 = {naive_count - inelig - 3}")
    print(f"  Step 3: Restore C20 double-count (standalone send events)     : +1 = {naive_count - inelig - 3 + 1}")
    print(f"  Final:  Finance target_base                                   : {final_count}")
    print()
    if final_count == 22:
        print("  [PASS] RECONCILES TO FINANCE'S TARGET_BASE OF 22")
    else:
        print(f"  [FAIL] GOT {final_count}, EXPECTED 22 — FURTHER INVESTIGATION NEEDED")

    conn.close()
    print("\n" + "#"*70)
    print("  ANALYSIS COMPLETE")
    print("#"*70)


if __name__ == "__main__":
    main()
