"""
final_audit.py — Audits DB, variables, path errors, and code anomalies (UTF-8 safe version).
"""
import sys
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

# Reconfigure stdout to use UTF-8 just in case
sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(".")
DB_PATH = ROOT / "data" / "db" / "bluestock_mf.db"

print("=" * 60)
print("             CAPSTONE CODEBASE AUDIT & ANALYSIS")
print("=" * 60)

# ── 1. DB HEALTH CHECK ────────────────────────────────────────────────────────
print("\n[1] DATABASE & TABLE CHECKS")
if not DB_PATH.exists():
    print(f"[FAIL] Error: Database not found at {DB_PATH}")
else:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table counts
    tables = [t[0] for t in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"Found {len(tables)} tables: {tables}")
    
    for table in tables:
        count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        # Check for NULLs in columns
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [c[1] for c in cursor.fetchall()]
        null_counts = {}
        for col in cols:
            nulls = cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE [{col}] IS NULL").fetchone()[0]
            if nulls > 0:
                null_counts[col] = nulls
        
        # Check if previous_nav, nav_change, nav_return_pct are the only NULLs in fact_nav (expected first rows of time series)
        null_str = f" | NULLs: {null_counts}" if null_counts else " | No NULL values"
        print(f"  - {table:18}: {count:6,} rows{null_str}")
        
    conn.close()

# ── 2. DATA PATH VALIDATION (No hardcoded absolute paths) ─────────────────────
print("\n[2] DATA PATH & ENVIRONMENT CHECK")
absolute_paths_found = []
py_files = list(ROOT.glob("scripts/*.py")) + list(ROOT.glob("dashboard/*.py"))
for py_file in py_files:
    content = py_file.read_text(encoding="utf-8")
    if "C:\\" in content or "C:/" in content or "/home/" in content or "OneDrive" in content:
        absolute_paths_found.append(f"  scripts/{py_file.name}: contains absolute/OneDrive references")

# Check notebooks for absolute paths in source code only
import json
notebooks = list(ROOT.glob("notebooks/*.ipynb"))
for nb_path in notebooks:
    try:
        nb_json = json.loads(nb_path.read_text(encoding="utf-8"))
        for i, cell in enumerate(nb_json.get("cells", [])):
            if cell.get("cell_type") == "code":
                src = "".join(cell.get("source", []))
                if "C:\\\\" in src or "C:/" in src or "/home/" in src or "OneDrive" in src:
                    absolute_paths_found.append(f"  notebooks/{nb_path.name} (Cell {i}): source contains absolute/OneDrive references")
    except Exception as e:
        absolute_paths_found.append(f"  notebooks/{nb_path.name}: Failed to parse JSON ({e})")

if absolute_paths_found:
    print("[FAIL] Path issues found:")
    for path_issue in absolute_paths_found:
        print(path_issue)
else:
    print("[PASS] No hardcoded absolute or environment-dependent paths found in Python scripts or Jupyter Notebooks.")

# ── 3. DATA QUALITY & ANOMALIES AUDIT (NAV, returns, gaps) ──────────────────
print("\n[3] DATA ANOMALIES & AUDIT")
if DB_PATH.exists():
    conn = sqlite3.connect(DB_PATH)
    
    # Check NAV sequence anomalies (outliers or daily jumps)
    df_nav = pd.read_sql_query("""
        SELECT f.scheme_name, d.calendar_date, n.nav
        FROM fact_nav n
        JOIN dim_fund f ON f.fund_key = n.fund_key
        JOIN dim_date d ON d.date_key = n.date_key
        ORDER BY f.scheme_name, d.calendar_date
    """, conn, parse_dates=["calendar_date"])
    
    df_nav["pct_change"] = df_nav.groupby("scheme_name")["nav"].pct_change()
    outliers = df_nav[df_nav["pct_change"].abs() > 0.10]
    
    if not outliers.empty:
        print(f"[WARN] Warning: Found {len(outliers)} daily NAV returns > 10% or < -10%:")
        for idx, row in outliers.iterrows():
            print(f"  - {row['scheme_name'].split(' - ')[0]}: {row['calendar_date'].date()} -> {row['pct_change']*100:.2f}% (NAV: {row['nav']})")
    else:
        print("[PASS] Daily returns: All within normal limits (+/- 10% daily deviation).")

    # Check for gaps in dates (should be sequential working days)
    df_nav["date_diff"] = df_nav.groupby("scheme_name")["calendar_date"].diff().dt.days
    date_gaps = df_nav[df_nav["date_diff"] > 5] # gaps longer than typical weekend/holidays (e.g. 5 days)
    if not date_gaps.empty:
        print(f"[WARN] Warning: Found {len(date_gaps)} NAV timeline gaps > 5 days:")
        for idx, row in date_gaps.head(5).iterrows():
            print(f"  - {row['scheme_name'].split(' - ')[0]}: gap of {row['date_diff']} days before {row['calendar_date'].date()}")
    else:
        print("[PASS] Date sequence: No gaps larger than typical weekend/holidays.")

    conn.close()

# ── 4. VERIFICATION OF INTERMEDIARY OUTPUTS (reports/) ───────────────────────
print("\n[4] INTERMEDIARY OUTPUTS (reports/)")
missing_reports = []
required_reports = [
    "Final_Report.pdf",
    "Presentation.pdf",
    "Presentation.pptx",
    "Dashboard.pdf",
    "monte_carlo_simulation.png",
    "efficient_frontier.png",
    "rolling_sharpe_chart.png",
    "var_cvar_report.csv"
]
for rep in required_reports:
    path = ROOT / "reports" / rep
    if not path.exists():
        missing_reports.append(rep)

if missing_reports:
    print(f"[FAIL] Missing required reports/assets: {missing_reports}")
else:
    print("[PASS] All required PDF reports, slides (PPTX), and visualization assets exist in reports/.")

print("\n" + "=" * 60)
print("                     AUDIT REPORT COMPLETE")
print("=" * 60)
