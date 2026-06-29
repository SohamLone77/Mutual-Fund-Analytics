#!/usr/bin/env python
from __future__ import annotations
import sys; sys.stdout.reconfigure(encoding="utf-8")
"""
data_cleaning.py — Day 2 Deliverable
======================================
Clean all raw NAV CSVs and load a SQLite star schema.

Pipeline:
    1. For each nav_*.csv -> clean dates, NAV, derive returns -> save *_clean.csv
    2. Fix HDFC Money Market NAV 100x split discontinuity (2015-08-30)
    3. Concatenate to nav_history_clean.csv
    4. Build dim_fund, dim_date, fact_nav, fact_aum star schema tables
    5. Generate synthetic dim_investor + fact_transactions (illustrative)
    6. Load all tables into bluestock_mf.db via SQLAlchemy

Usage:
    python src/data_cleaning.py
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

ROOT          = Path(__file__).resolve().parents[1]
RAW_DIR       = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
DB_PATH       = ROOT / "bluestock_mf.db"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# HDFC Money Market (amfi_code 119092) had a 100× unit consolidation on 2015-08-30.
# Pre-split NAVs (~23–30) must be scaled ×100 to match post-split NAVs (~3000+).
HDFC_AMFI_CODE  = 119092
HDFC_SPLIT_DATE = pd.Timestamp("2015-08-30")


# ═══════════════════════════════════════════════════════════════════════════════
# NAV Cleaning
# ═══════════════════════════════════════════════════════════════════════════════

class NAVCleaner:
    """Cleans a single raw NAV CSV into a standardised DataFrame."""

    @staticmethod
    def _read_meta(json_path: Path) -> dict:
        if not json_path.exists():
            return {}
        with json_path.open(encoding="utf-8") as f:
            return json.load(f).get("meta", {})

    @staticmethod
    def _clean_text(value: object) -> str:
        if pd.isna(value):
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()

    @staticmethod
    def _parse_date(series: pd.Series) -> pd.Series:
        parsed = pd.to_datetime(series, errors="coerce")
        if parsed.notna().any():
            return parsed
        return pd.to_datetime(series, errors="coerce", dayfirst=True)

    def clean(self, csv_path: Path) -> pd.DataFrame:
        df   = pd.read_csv(csv_path).rename(columns=str.lower)
        meta = self._read_meta(csv_path.with_suffix(".json"))

        if "scheme_code" in df.columns:
            df = df.rename(columns={"scheme_code": "amfi_code"})

        df["amfi_code"]   = pd.to_numeric(df["amfi_code"], errors="coerce").astype("Int64")
        df["date"]        = self._parse_date(df["date"])
        df["nav"]         = pd.to_numeric(df["nav"], errors="coerce")
        df["source_file"] = csv_path.name

        text_cols = ["scheme_name", "fund_house", "scheme_type",
                     "scheme_category", "isin_growth", "isin_div_reinvestment"]
        for col in text_cols:
            if col not in df.columns:
                df[col] = meta.get(col, "")
            df[col] = df[col].map(self._clean_text)

        df = (df
              .dropna(subset=["amfi_code", "date"])
              .sort_values(["amfi_code", "date"])
              .drop_duplicates(subset=["amfi_code", "date"], keep="last"))

        df["nav"] = df.groupby("amfi_code")["nav"].ffill().bfill()
        df = df.loc[df["nav"].notna() & (df["nav"] > 0)].copy()

        # Fix HDFC 100× split discontinuity
        if df["amfi_code"].iloc[0] == HDFC_AMFI_CODE:
            pre_split = df["date"] < HDFC_SPLIT_DATE
            df.loc[pre_split, "nav"] = df.loc[pre_split, "nav"] * 100

        df["previous_nav"]   = df.groupby("amfi_code")["nav"].shift(1)
        df["nav_change"]     = df["nav"] - df["previous_nav"]
        df["nav_return_pct"] = np.where(
            df["previous_nav"].notna() & (df["previous_nav"] != 0),
            (df["nav_change"] / df["previous_nav"]) * 100,
            np.nan,
        )

        return df[[
            "amfi_code", "date", "nav", "scheme_name", "fund_house",
            "scheme_type", "scheme_category", "isin_growth",
            "isin_div_reinvestment", "source_file",
            "previous_nav", "nav_change", "nav_return_pct",
        ]].reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Star Schema Builder
# ═══════════════════════════════════════════════════════════════════════════════

class StarSchemaBuilder:
    """Builds the dim/fact tables from the cleaned NAV history."""

    def build(self, nav_history: pd.DataFrame) -> dict[str, pd.DataFrame]:
        dim_fund = self._build_dim_fund(nav_history)
        dim_date = self._build_dim_date(nav_history)
        fact_nav = self._build_fact_nav(nav_history, dim_fund)
        fact_aum = self._build_fact_aum(nav_history, dim_fund)
        dim_investor, fact_transactions = self._build_synthetic_activity(nav_history, dim_fund)

        return {
            "dim_fund":          dim_fund,
            "dim_date":          dim_date,
            "fact_nav":          fact_nav,
            "fact_aum":          fact_aum,
            "dim_investor":      dim_investor,
            "fact_transactions": fact_transactions,
        }

    # ── Dimensions ─────────────────────────────────────────────────────────────

    @staticmethod
    def _build_dim_fund(nav: pd.DataFrame) -> pd.DataFrame:
        dim = (nav[[
            "amfi_code", "scheme_name", "fund_house", "scheme_type",
            "scheme_category", "isin_growth", "isin_div_reinvestment", "source_file",
        ]]
        .drop_duplicates(subset=["amfi_code"])
        .sort_values(["fund_house", "scheme_name", "amfi_code"])
        .reset_index(drop=True))
        dim.insert(0, "fund_key", range(1, len(dim) + 1))
        return dim

    @staticmethod
    def _build_dim_date(nav: pd.DataFrame) -> pd.DataFrame:
        dates = pd.DataFrame({
            "calendar_date": pd.date_range(nav["date"].min(), nav["date"].max(), freq="D"),
        })
        dates["date_key"]     = dates["calendar_date"].dt.strftime("%Y%m%d").astype(int)
        dates["year"]         = dates["calendar_date"].dt.year
        dates["quarter"]      = dates["calendar_date"].dt.quarter
        dates["month"]        = dates["calendar_date"].dt.month
        dates["month_name"]   = dates["calendar_date"].dt.strftime("%B")
        dates["day"]          = dates["calendar_date"].dt.day
        dates["day_name"]     = dates["calendar_date"].dt.strftime("%A")
        dates["week_of_year"] = dates["calendar_date"].dt.isocalendar().week.astype(int)
        dates["is_weekend"]   = dates["calendar_date"].dt.dayofweek.ge(5).astype(int)
        dates["is_month_start"] = dates["calendar_date"].dt.is_month_start.astype(int)
        dates["is_month_end"]   = dates["calendar_date"].dt.is_month_end.astype(int)
        return dates[[
            "date_key", "calendar_date", "year", "quarter", "month", "month_name",
            "day", "day_name", "week_of_year", "is_weekend", "is_month_start", "is_month_end",
        ]]

    # ── Facts ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_fact_nav(nav: pd.DataFrame, dim_fund: pd.DataFrame) -> pd.DataFrame:
        fact = nav.merge(dim_fund[["fund_key", "amfi_code"]], on="amfi_code", how="left")
        fact["date_key"] = fact["date"].dt.strftime("%Y%m%d").astype(int)
        fact = fact[[
            "fund_key", "date_key", "nav", "previous_nav",
            "nav_change", "nav_return_pct", "source_file",
        ]].copy()
        fact.insert(0, "fact_nav_key", range(1, len(fact) + 1))
        return fact

    @staticmethod
    def _build_fact_aum(nav: pd.DataFrame, dim_fund: pd.DataFrame) -> pd.DataFrame:
        summary = (nav.sort_values(["amfi_code", "date"])
                      .groupby("amfi_code", as_index=False)
                      .agg(
                          latest_date=("date", "last"),
                          observation_count=("nav", "size"),
                          min_nav=("nav", "min"),
                          max_nav=("nav", "max"),
                          aum_value=("nav", "last"),
                      ))
        fact = summary.merge(dim_fund[["fund_key", "amfi_code", "source_file"]], on="amfi_code", how="left")
        fact["date_key"]     = fact["latest_date"].dt.strftime("%Y%m%d").astype(int)
        fact["proxy_method"] = "latest_nav"
        fact = fact[[
            "fund_key", "date_key", "aum_value", "observation_count",
            "min_nav", "max_nav", "proxy_method", "source_file",
        ]].copy()
        fact.insert(0, "aum_key", range(1, len(fact) + 1))
        return fact

    # ── Synthetic investor / transaction activity (illustrative) ───────────────

    @staticmethod
    def _build_synthetic_activity(
        nav: pd.DataFrame, dim_fund: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        rng = np.random.default_rng(42)

        # ── dim_investor (250 synthetic investors) ────────────────────────────
        AGE_GROUPS  = ["18-25", "26-35", "36-45", "46-55", "56-65", "65+"]
        AGE_PROBS   = [0.08, 0.22, 0.30, 0.20, 0.12, 0.08]
        AGE_SIP     = {"18-25": 2200, "26-35": 3200, "36-45": 4500,
                       "46-55": 3800, "56-65": 2800, "65+": 1800}
        STATES      = ["Maharashtra", "Gujarat", "Karnataka", "Tamil Nadu",
                       "Delhi", "Uttar Pradesh", "Rajasthan", "West Bengal",
                       "Telangana", "Andhra Pradesh"]
        date_pool   = pd.date_range(nav["date"].min(), nav["date"].max(), freq="15D")

        investors = []
        for i in range(1, 251):
            ag  = rng.choice(AGE_GROUPS, p=AGE_PROBS)
            sip = float(max(500, rng.normal(AGE_SIP[ag], AGE_SIP[ag] * 0.18)))
            investors.append({
                "investor_id":       f"INV{i:05d}",
                "age_group":         ag,
                "gender":            rng.choice(["Male", "Female"], p=[0.68, 0.32]),
                "state":             rng.choice(STATES),
                "city_tier":         rng.choice(["T30", "B30"], p=[0.72, 0.28]),
                "registration_date": pd.Timestamp(rng.choice(date_pool)).strftime("%Y-%m-%d"),
                "sip_amount":        round(sip, 2),
                "source_file":       "synthetic_investors",
            })
        dim_investor = pd.DataFrame(investors)

        # ── fact_transactions (monthly SIP / lumpsum activity, 2022–2025) ─────
        month_starts = pd.date_range("2022-01-01", "2025-12-01", freq="MS")
        transactions = []
        for mi, month_start in enumerate(month_starts):
            active  = dim_investor.sample(frac=0.35, random_state=mi)
            monthly_base = 15000 + (mi / max(len(month_starts) - 1, 1)) * (31002 - 15000)
            for pi, inv in active.reset_index(drop=True).iterrows():
                fund_row = dim_fund.sample(1, random_state=mi * 1000 + pi).iloc[0]
                txn_type = "SIP" if rng.random() < 0.82 else "LUMPSUM"
                amount   = max(500.0, rng.normal(monthly_base * (1.0 if txn_type == "SIP" else 1.6), 2500))
                units    = amount / max(float(rng.uniform(10, 250)), 1)
                transactions.append({
                    "fund_key":              int(fund_row["fund_key"]),
                    "transaction_date_key":  int(month_start.strftime("%Y%m%d")),
                    "investor_id":           inv["investor_id"],
                    "transaction_type":      txn_type,
                    "amount":                round(float(amount), 2),
                    "units":                 round(float(units), 2),
                    "nav":                   round(float(rng.uniform(10, 250)), 2),
                    "state":                 inv["state"],
                    "kyc_status":            "Verified" if rng.random() < 0.90 else "Pending",
                    "source_file":           "synthetic_transactions",
                })

        fact_txn = pd.DataFrame(transactions)
        fact_txn.insert(0, "transaction_key", range(1, len(fact_txn) + 1))
        return dim_investor, fact_txn


# ═══════════════════════════════════════════════════════════════════════════════
# SQLite Loader
# ═══════════════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_fund (
    fund_key              INTEGER PRIMARY KEY,
    amfi_code             INTEGER NOT NULL UNIQUE,
    scheme_name           TEXT    NOT NULL,
    fund_house            TEXT,
    scheme_type           TEXT,
    scheme_category       TEXT,
    isin_growth           TEXT,
    isin_div_reinvestment TEXT,
    source_file           TEXT,
    created_at            TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key      INTEGER PRIMARY KEY,
    calendar_date TEXT    NOT NULL UNIQUE,
    year          INTEGER NOT NULL,
    quarter       INTEGER NOT NULL,
    month         INTEGER NOT NULL,
    month_name    TEXT    NOT NULL,
    day           INTEGER NOT NULL,
    day_name      TEXT    NOT NULL,
    week_of_year  INTEGER NOT NULL,
    is_weekend    INTEGER NOT NULL,
    is_month_start INTEGER NOT NULL,
    is_month_end   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_nav (
    fact_nav_key INTEGER PRIMARY KEY,
    fund_key     INTEGER NOT NULL,
    date_key     INTEGER NOT NULL,
    nav          REAL    NOT NULL,
    previous_nav REAL,
    nav_change   REAL,
    nav_return_pct REAL,
    source_file  TEXT,
    FOREIGN KEY (fund_key) REFERENCES dim_fund (fund_key),
    FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    UNIQUE (fund_key, date_key)
);

CREATE TABLE IF NOT EXISTS fact_transactions (
    transaction_key      INTEGER PRIMARY KEY,
    fund_key             INTEGER,
    transaction_date_key INTEGER,
    investor_id          TEXT,
    transaction_type     TEXT,
    amount               REAL,
    units                REAL,
    nav                  REAL,
    state                TEXT,
    kyc_status           TEXT,
    source_file          TEXT,
    FOREIGN KEY (fund_key)             REFERENCES dim_fund (fund_key),
    FOREIGN KEY (transaction_date_key) REFERENCES dim_date (date_key)
);

CREATE TABLE IF NOT EXISTS fact_performance (
    performance_key INTEGER PRIMARY KEY,
    fund_key        INTEGER,
    date_key        INTEGER,
    return_1m       REAL,
    return_3m       REAL,
    return_1y       REAL,
    return_3y       REAL,
    return_5y       REAL,
    expense_ratio   REAL,
    volatility      REAL,
    sharpe_ratio    REAL,
    anomaly_flag    INTEGER NOT NULL DEFAULT 0,
    source_file     TEXT,
    FOREIGN KEY (fund_key) REFERENCES dim_fund (fund_key),
    FOREIGN KEY (date_key) REFERENCES dim_date (date_key)
);

CREATE TABLE IF NOT EXISTS fact_aum (
    aum_key           INTEGER PRIMARY KEY,
    fund_key          INTEGER NOT NULL,
    date_key          INTEGER NOT NULL,
    aum_value         REAL    NOT NULL,
    observation_count INTEGER,
    min_nav           REAL,
    max_nav           REAL,
    proxy_method      TEXT    NOT NULL,
    source_file       TEXT,
    FOREIGN KEY (fund_key) REFERENCES dim_fund (fund_key),
    FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    UNIQUE (fund_key, date_key)
);

CREATE TABLE IF NOT EXISTS dim_investor (
    investor_id       TEXT PRIMARY KEY,
    age_group         TEXT,
    gender            TEXT,
    state             TEXT,
    city_tier         TEXT,
    registration_date TEXT,
    sip_amount        REAL,
    source_file       TEXT
);
""".strip()


def load_sqlite(frames: dict[str, pd.DataFrame]) -> None:
    engine = create_engine(f"sqlite:///{DB_PATH.resolve().as_posix()}")

    drop_order = [
        "fact_transactions", "fact_performance", "fact_aum",
        "fact_nav", "dim_investor", "dim_date", "dim_fund",
    ]
    with engine.begin() as con:
        for tbl in drop_order:
            con.exec_driver_sql(f"DROP TABLE IF EXISTS {tbl}")
        for stmt in [s.strip() for s in SCHEMA_SQL.split(";") if s.strip()]:
            con.exec_driver_sql(stmt)

    load_order = [
        "dim_fund", "dim_date", "fact_nav", "fact_aum",
        "dim_investor", "fact_transactions",
    ]
    for tbl in load_order:
        frames[tbl].to_sql(tbl, engine, if_exists="append", index=False)

    # Empty fact_performance placeholder
    pd.DataFrame(columns=[
        "fund_key", "date_key", "return_1m", "return_3m", "return_1y",
        "return_3y", "return_5y", "expense_ratio", "volatility",
        "sharpe_ratio", "anomaly_flag", "source_file",
    ]).to_sql("fact_performance", engine, if_exists="append", index=False)

    # Row-count verification
    print("\nRow counts (loaded / expected):")
    expected = {t: len(frames[t]) for t in load_order}
    expected["fact_performance"] = 0
    with engine.connect() as con:
        for tbl, exp in expected.items():
            actual = con.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar_one()
            status = "OK" if actual == exp else "MISMATCH"
            print(f"  {tbl:<25} {actual:>7,} / {exp:<7,}  [{status}]")


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    cleaner = NAVCleaner()
    builder = StarSchemaBuilder()
    nav_frames: list[pd.DataFrame] = []

    for csv_path in sorted(RAW_DIR.glob("nav_*.csv")):
        cleaned = cleaner.clean(csv_path)
        out = PROCESSED_DIR / f"{csv_path.stem}_clean.csv"
        cleaned.to_csv(out, index=False)
        print(f"Cleaned {csv_path.name} -> {len(cleaned):,} rows")
        nav_frames.append(cleaned)

    nav_history = pd.concat(nav_frames, ignore_index=True).sort_values(["amfi_code", "date"])
    nav_history.to_csv(PROCESSED_DIR / "nav_history_clean.csv", index=False)
    print(f"\nnav_history_clean.csv  -> {len(nav_history):,} rows total")

    frames = builder.build(nav_history)
    for name, df in frames.items():
        df.to_csv(PROCESSED_DIR / f"{name}.csv", index=False)

    load_sqlite(frames)
    print("\nDone — bluestock_mf.db ready.")


if __name__ == "__main__":
    main()