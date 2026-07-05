#!/usr/bin/env python
"""
live_nav_fetch.py — Day 1 Deliverable
=======================================
Fetch live NAV history for 6 key schemes from mfapi.in.
Saves raw JSON + cleaned CSV per scheme, plus a summary CSV.

Schemes fetched:
    125497 — SBI Small Cap Direct
    119551 — Aditya Birla Sun Life Banking & PSU Debt Direct
    120503 — Axis ELSS Tax Saver Direct
    118632 — Nippon India Large Cap Direct
    119092 — HDFC Money Market Direct
    120841 — quant Mid Cap Direct

Usage:
    python src/live_nav_fetch.py
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

ROOT     = Path(__file__).resolve().parents[1]
RAW_DIR  = ROOT / "data" / "raw"
RPT_DIR  = ROOT / "reports"
RAW_DIR.mkdir(parents=True, exist_ok=True)
RPT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://api.mfapi.in/mf"

SCHEMES: dict[str, str] = {
    "125497": "SBI Small Cap Direct",
    "119551": "Aditya Birla Banking & PSU Debt Direct",
    "120503": "Axis ELSS Tax Saver Direct",
    "118632": "Nippon India Large Cap Direct",
    "119092": "HDFC Money Market Direct",
    "120841": "quant Mid Cap Direct",
}


# ── Core fetch ────────────────────────────────────────────────────────────────

def fetch_scheme(amfi_code: str) -> dict | None:
    """Fetch all NAV history for one scheme; returns parsed JSON or None."""
    try:
        response = requests.get(f"{BASE_URL}/{amfi_code}", timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        print(f"  ERROR fetching {amfi_code}: {exc}")
        return None


def save_raw(amfi_code: str, payload: dict, date_tag: str) -> Path:
    """Persist raw API response as JSON."""
    path = RAW_DIR / f"nav_{amfi_code}_{date_tag}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return path


def payload_to_csv(amfi_code: str, payload: dict, date_tag: str) -> pd.DataFrame | None:
    """Convert mfapi.in JSON payload to a clean DataFrame and save as CSV."""
    nav_records = payload.get("data", [])
    meta        = payload.get("meta", {})

    if not nav_records:
        print(f"  No NAV records returned for {amfi_code}")
        return None

    df = pd.DataFrame(nav_records)                        # columns: date, nav
    df["date"]        = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
    df["nav"]         = pd.to_numeric(df["nav"], errors="coerce")
    df["amfi_code"]   = int(amfi_code)
    df["scheme_name"] = meta.get("scheme_name", "")
    df["fund_house"]  = meta.get("fund_house", "")
    df["scheme_type"] = meta.get("scheme_type", "")
    df["scheme_category"] = meta.get("scheme_category", "")

    df = (df
          .dropna(subset=["date", "nav"])
          .query("nav > 0")
          .sort_values("date")
          .drop_duplicates(subset=["amfi_code", "date"])
          .reset_index(drop=True))

    path = RAW_DIR / f"nav_{amfi_code}_{date_tag}.csv"
    df.to_csv(path, index=False)
    return df


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    date_tag = datetime.now().strftime("%Y%m%d")
    summary_rows: list[dict] = []

    print(f"Fetching NAV data from {BASE_URL}")
    print(f"Date tag: {date_tag}\n")

    for amfi_code, label in SCHEMES.items():
        print(f"  {amfi_code}  {label}")
        payload = fetch_scheme(amfi_code)

        if payload is None:
            continue

        json_path = save_raw(amfi_code, payload, date_tag)
        df        = payload_to_csv(amfi_code, payload, date_tag)

        if df is None:
            continue

        meta = payload.get("meta", {})
        summary_rows.append({
            "amfi_code":      amfi_code,
            "scheme_name":    meta.get("scheme_name", label),
            "fund_house":     meta.get("fund_house", ""),
            "total_entries":  len(df),
            "date_from":      str(df["date"].min().date()),
            "date_to":        str(df["date"].max().date()),
            "latest_nav":     round(float(df["nav"].iloc[-1]), 4),
            "min_nav":        round(float(df["nav"].min()), 4),
            "max_nav":        round(float(df["nav"].max()), 4),
        })

        print(f"    Saved {len(df):,} rows  |  NAV range: "
              f"{df['date'].min().date()} → {df['date'].max().date()}  |  "
              f"Latest NAV: {df['nav'].iloc[-1]:.2f}")

        time.sleep(0.8)   # respect API rate limit

    # ── Summary CSV ───────────────────────────────────────────────────────────
    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        summary_path = RPT_DIR / "nav_fetch_summary.csv"
        summary_df.to_csv(summary_path, index=False)

        print(f"\nFetched {len(summary_rows)} / {len(SCHEMES)} schemes")
        print(f"Summary saved → {summary_path}")
        print(summary_df.to_string(index=False))
    else:
        print("No data fetched — check network / API availability.")


if __name__ == "__main__":
    main()