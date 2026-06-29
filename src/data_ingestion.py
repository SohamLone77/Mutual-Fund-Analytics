#!/usr/bin/env python
"""
data_ingestion.py — Day 1 Deliverable
======================================
Load all raw NAV CSVs, validate structure & quality, produce data quality report.

Usage:
    python src/data_ingestion.py
"""
from __future__ import annotations

import os
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT       = Path(__file__).resolve().parents[1]
RAW_DIR    = ROOT / "data" / "raw"
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_scheme_meta(csv_path: Path) -> dict:
    """Read JSON sidecar for scheme metadata (fund_house, category, etc.)."""
    json_path = csv_path.with_suffix(".json")
    if not json_path.exists():
        return {}
    with json_path.open(encoding="utf-8") as f:
        return json.load(f).get("meta", {})


def inspect_dataset(df: pd.DataFrame, name: str) -> dict:
    """Print shape / dtypes / head and return a quality metrics dict."""
    print(f"\n{'='*60}")
    print(f"Dataset : {name}")
    print(f"Shape   : {df.shape[0]:,} rows x {df.shape[1]} columns")
    print(f"Columns : {list(df.columns)}")
    print("\ndtypes:")
    print(df.dtypes.to_string())
    print("\nHead (3 rows):")
    print(df.head(3).to_string(index=False))

    missing  = int(df.isnull().sum().sum())
    dupes    = int(df.duplicated().sum())
    neg_nav  = 0
    anomalies: list[str] = []

    if "nav" in df.columns:
        neg_nav = int((pd.to_numeric(df["nav"], errors="coerce") <= 0).sum())
        if neg_nav:
            anomalies.append(f"{neg_nav} rows with NAV <= 0")

    if missing:
        anomalies.append(f"{missing} missing values")
    if dupes:
        anomalies.append(f"{dupes} duplicate rows")
    if anomalies:
        print(f"\n[WARN] Anomalies: {'; '.join(anomalies)}")
    else:
        print("\n[OK] No anomalies detected")

    return {
        "name":        name,
        "rows":        df.shape[0],
        "columns":     df.shape[1],
        "missing":     missing,
        "duplicates":  dupes,
        "neg_nav":     neg_nav,
        "anomalies":   "; ".join(anomalies) if anomalies else "none",
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    csv_files = sorted(RAW_DIR.glob("nav_*.csv"))
    if not csv_files:
        print(f"No CSV files found in {RAW_DIR}")
        return

    print(f"Found {len(csv_files)} raw NAV files\n")

    quality_rows: list[dict] = []

    for csv_path in csv_files:
        df = pd.read_csv(csv_path)

        # Attach metadata from JSON sidecar
        meta = load_scheme_meta(csv_path)
        for field in ("scheme_name", "fund_house", "scheme_category", "scheme_type"):
            if field not in df.columns:
                df[field] = meta.get(field, "")

        quality_rows.append(inspect_dataset(df, csv_path.name))

    # ── Summary table ─────────────────────────────────────────────────────────
    qdf = pd.DataFrame(quality_rows)
    print(f"\n\n{'='*60}")
    print("DATA QUALITY SUMMARY")
    print('='*60)
    print(qdf.to_string(index=False))

    # ── Unique fund metadata ──────────────────────────────────────────────────
    all_frames = []
    for csv_path in csv_files:
        df = pd.read_csv(csv_path)
        meta = load_scheme_meta(csv_path)
        for field in ("scheme_name", "fund_house", "scheme_category", "scheme_type"):
            if field not in df.columns:
                df[field] = meta.get(field, "")
        all_frames.append(df[["fund_house", "scheme_category", "scheme_type", "scheme_name"]].drop_duplicates())

    fund_master = pd.concat(all_frames, ignore_index=True).drop_duplicates()

    print(f"\nUnique Fund Houses  : {fund_master['fund_house'].nunique()}")
    print(f"Unique Categories   : {fund_master['scheme_category'].nunique()}")
    print(f"Unique Scheme Types : {fund_master['scheme_type'].nunique()}")
    print("\nFund master preview:")
    print(fund_master.to_string(index=False))

    # ── AMFI code validation ──────────────────────────────────────────────────
    # Every amfi_code in fund_master should appear in NAV files
    nav_codes = set()
    for csv_path in csv_files:
        df = pd.read_csv(csv_path)
        col = "scheme_code" if "scheme_code" in df.columns else ("amfi_code" if "amfi_code" in df.columns else None)
        if col:
            nav_codes.update(df[col].dropna().astype(int).tolist())

    # Codes embedded in filenames (e.g. nav_118632_*.csv)
    filename_codes = set()
    for p in csv_files:
        parts = p.stem.split("_")
        for part in parts:
            if part.isdigit() and len(part) >= 5:
                filename_codes.add(int(part))

    print(f"\nAMFI codes found in NAV files   : {sorted(nav_codes)}")
    print(f"AMFI codes extracted from names : {sorted(filename_codes)}")
    missing_codes = filename_codes - nav_codes
    if missing_codes:
        print(f"[WARN] AMFI codes in filenames but not in data: {missing_codes}")
    else:
        print("[OK] All AMFI codes validated")

    # ── Save quality report ───────────────────────────────────────────────────
    report_path = REPORT_DIR / "data_quality_report.txt"
    with report_path.open("w", encoding="utf-8") as f:
        f.write("DATA QUALITY REPORT\n")
        f.write("="*60 + "\n\n")
        for row in quality_rows:
            f.write(f"File      : {row['name']}\n")
            f.write(f"Rows      : {row['rows']:,}\n")
            f.write(f"Columns   : {row['columns']}\n")
            f.write(f"Missing   : {row['missing']}\n")
            f.write(f"Duplicates: {row['duplicates']}\n")
            f.write(f"Anomalies : {row['anomalies']}\n\n")

    print(f"\nQuality report saved -> {report_path}")


if __name__ == "__main__":
    main()