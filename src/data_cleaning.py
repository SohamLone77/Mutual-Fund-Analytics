#!/usr/bin/env python
"""Clean mutual fund NAV data and load a small SQLite star schema."""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


ROOT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"
DB_PATH = ROOT_DIR / "bluestock_mf.db"
SCHEMA_PATH = ROOT_DIR / "schema.sql"
QUERIES_PATH = ROOT_DIR / "queries.sql"
DICTIONARY_PATH = ROOT_DIR / "data_dictionary.md"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_fund (
    fund_key INTEGER PRIMARY KEY,
    amfi_code INTEGER NOT NULL UNIQUE,
    scheme_name TEXT NOT NULL,
    fund_house TEXT,
    scheme_type TEXT,
    scheme_category TEXT,
    isin_growth TEXT,
    isin_div_reinvestment TEXT,
    source_file TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER PRIMARY KEY,
    calendar_date TEXT NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    day INTEGER NOT NULL,
    day_name TEXT NOT NULL,
    week_of_year INTEGER NOT NULL,
    is_weekend INTEGER NOT NULL,
    is_month_start INTEGER NOT NULL,
    is_month_end INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_nav (
    fact_nav_key INTEGER PRIMARY KEY,
    fund_key INTEGER NOT NULL,
    date_key INTEGER NOT NULL,
    nav REAL NOT NULL,
    previous_nav REAL,
    nav_change REAL,
    nav_return_pct REAL,
    source_file TEXT,
    FOREIGN KEY (fund_key) REFERENCES dim_fund (fund_key),
    FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    UNIQUE (fund_key, date_key)
);

CREATE TABLE IF NOT EXISTS fact_transactions (
    transaction_key INTEGER PRIMARY KEY,
    fund_key INTEGER,
    transaction_date_key INTEGER,
    investor_id TEXT,
    transaction_type TEXT,
    amount REAL,
    units REAL,
    nav REAL,
    state TEXT,
    kyc_status TEXT,
    source_file TEXT,
    FOREIGN KEY (fund_key) REFERENCES dim_fund (fund_key),
    FOREIGN KEY (transaction_date_key) REFERENCES dim_date (date_key)
);

CREATE TABLE IF NOT EXISTS fact_performance (
    performance_key INTEGER PRIMARY KEY,
    fund_key INTEGER,
    date_key INTEGER,
    return_1m REAL,
    return_3m REAL,
    return_1y REAL,
    return_3y REAL,
    return_5y REAL,
    expense_ratio REAL,
    volatility REAL,
    sharpe_ratio REAL,
    anomaly_flag INTEGER NOT NULL DEFAULT 0,
    source_file TEXT,
    FOREIGN KEY (fund_key) REFERENCES dim_fund (fund_key),
    FOREIGN KEY (date_key) REFERENCES dim_date (date_key)
);

CREATE TABLE IF NOT EXISTS fact_aum (
    aum_key INTEGER PRIMARY KEY,
    fund_key INTEGER NOT NULL,
    date_key INTEGER NOT NULL,
    aum_value REAL NOT NULL,
    observation_count INTEGER,
    min_nav REAL,
    max_nav REAL,
    proxy_method TEXT NOT NULL,
    source_file TEXT,
    FOREIGN KEY (fund_key) REFERENCES dim_fund (fund_key),
    FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    UNIQUE (fund_key, date_key)
);
""".strip()


QUERIES_SQL = """
SELECT f.scheme_name, f.fund_house, a.aum_value, a.observation_count, a.proxy_method
FROM fact_aum a
JOIN dim_fund f ON f.fund_key = a.fund_key
ORDER BY a.aum_value DESC
LIMIT 5;

SELECT d.year, d.month, d.month_name, ROUND(AVG(n.nav), 4) AS average_nav
FROM fact_nav n
JOIN dim_date d ON d.date_key = n.date_key
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;

WITH sip_by_year AS (
    SELECT d.year, SUM(t.amount) AS sip_amount
    FROM fact_transactions t
    JOIN dim_date d ON d.date_key = t.transaction_date_key
    WHERE t.transaction_type = 'SIP'
    GROUP BY d.year
)
SELECT
    year,
    sip_amount,
    ROUND(
        100.0 * (sip_amount - LAG(sip_amount) OVER (ORDER BY year))
        / NULLIF(LAG(sip_amount) OVER (ORDER BY year), 0),
        2
    ) AS yoy_growth_pct
FROM sip_by_year
ORDER BY year;

SELECT COALESCE(state, 'Unknown') AS state, COUNT(*) AS transaction_count, ROUND(SUM(amount), 2) AS total_amount
FROM fact_transactions
GROUP BY COALESCE(state, 'Unknown')
ORDER BY transaction_count DESC, total_amount DESC;

SELECT f.scheme_name, f.fund_house, p.expense_ratio
FROM fact_performance p
JOIN dim_fund f ON f.fund_key = p.fund_key
WHERE p.expense_ratio < 1.0
ORDER BY p.expense_ratio ASC;

SELECT f.scheme_name, d.calendar_date, n.nav, n.previous_nav, (n.nav - n.previous_nav) AS nav_change
FROM fact_nav n
JOIN dim_fund f ON f.fund_key = n.fund_key
JOIN dim_date d ON d.date_key = n.date_key
WHERE n.previous_nav IS NOT NULL
ORDER BY ABS(n.nav - n.previous_nav) DESC
LIMIT 10;

SELECT f.fund_house, d.year, d.month, ROUND(AVG(n.nav), 4) AS average_nav
FROM fact_nav n
JOIN dim_fund f ON f.fund_key = n.fund_key
JOIN dim_date d ON d.date_key = n.date_key
GROUP BY f.fund_house, d.year, d.month
ORDER BY f.fund_house, d.year, d.month;

SELECT f.scheme_name, f.fund_house, COUNT(*) AS nav_observations, MIN(d.calendar_date) AS first_observation, MAX(d.calendar_date) AS latest_observation
FROM fact_nav n
JOIN dim_fund f ON f.fund_key = n.fund_key
JOIN dim_date d ON d.date_key = n.date_key
GROUP BY f.scheme_name, f.fund_house
ORDER BY nav_observations DESC
LIMIT 10;

SELECT f.scheme_name, COUNT(*) AS anomaly_rows
FROM fact_performance p
JOIN dim_fund f ON f.fund_key = p.fund_key
WHERE p.anomaly_flag = 1
GROUP BY f.scheme_name
ORDER BY anomaly_rows DESC, f.scheme_name;

SELECT f.scheme_name, d.calendar_date, n.nav
FROM fact_nav n
JOIN dim_fund f ON f.fund_key = n.fund_key
JOIN dim_date d ON d.date_key = n.date_key
WHERE d.is_month_end = 1
ORDER BY f.scheme_name, d.calendar_date;
""".strip()


DATA_DICTIONARY_MD = """
# Mutual Fund Data Dictionary

## Source Files
- `data/raw/nav_*.csv`: NAV history extracts per scheme.
- `data/raw/nav_*.json`: scheme metadata and NAV history payloads.
- `reports/nav_fetch_summary.csv`: high-level NAV summary used for proxy AUM aggregation.

## nav_history_clean.csv
| Column | Type | Business Definition | Source |
| --- | --- | --- | --- |
| amfi_code | INTEGER | Unique AMFI scheme identifier. | Raw CSV / JSON metadata |
| date | DATE | NAV observation date. | Raw NAV CSV and JSON payload |
| nav | REAL | Daily net asset value. | Raw NAV CSV / JSON payload |
| scheme_name | TEXT | Human-readable fund name. | Raw CSV / JSON meta |
| fund_house | TEXT | Asset management company name. | Raw CSV / JSON meta |
| scheme_type | TEXT | Scheme family. | Raw JSON meta |
| scheme_category | TEXT | Fund category. | Raw JSON meta |
| isin_growth | TEXT | Growth option ISIN. | Raw JSON meta |
| isin_div_reinvestment | TEXT | Dividend/reinvestment option ISIN. | Raw JSON meta |
| source_file | TEXT | Originating raw file name. | File system |
| previous_nav | REAL | Previous NAV for the same fund. | Derived |
| nav_change | REAL | Day-over-day NAV change. | Derived |
| nav_return_pct | REAL | Day-over-day NAV return percentage. | Derived |

## dim_fund
| Column | Type | Business Definition | Source |
| --- | --- | --- | --- |
| fund_key | INTEGER | Surrogate primary key. | Derived |
| amfi_code | INTEGER | Natural fund key. | Cleaned NAV history |
| scheme_name | TEXT | Fund name. | Cleaned NAV history |
| fund_house | TEXT | AMC name. | Cleaned NAV history |
| scheme_type | TEXT | Scheme family. | Raw JSON meta |
| scheme_category | TEXT | Fund category. | Raw JSON meta |
| isin_growth | TEXT | Growth ISIN. | Raw JSON meta |
| isin_div_reinvestment | TEXT | Dividend/reinvestment ISIN. | Raw JSON meta |
| source_file | TEXT | Source file. | Cleaned NAV history |
| created_at | TEXT | Row creation timestamp. | SQLite default |

## dim_date
| Column | Type | Business Definition | Source |
| --- | --- | --- | --- |
| date_key | INTEGER | YYYYMMDD surrogate key. | Derived |
| calendar_date | TEXT | ISO calendar date. | Derived |
| year | INTEGER | Calendar year. | Derived |
| quarter | INTEGER | Calendar quarter. | Derived |
| month | INTEGER | Calendar month number. | Derived |
| month_name | TEXT | Month name. | Derived |
| day | INTEGER | Day of month. | Derived |
| day_name | TEXT | Weekday name. | Derived |
| week_of_year | INTEGER | ISO week number. | Derived |
| is_weekend | INTEGER | Weekend indicator. | Derived |
| is_month_start | INTEGER | Month-start indicator. | Derived |
| is_month_end | INTEGER | Month-end indicator. | Derived |

## fact_nav
| Column | Type | Business Definition | Source |
| --- | --- | --- | --- |
| fact_nav_key | INTEGER | Surrogate fact key. | Derived |
| fund_key | INTEGER | Links to dim_fund. | Cleaned NAV history |
| date_key | INTEGER | Links to dim_date. | Cleaned NAV history |
| nav | REAL | Observed NAV value. | Cleaned NAV history |
| previous_nav | REAL | Prior NAV value for the same fund. | Derived |
| nav_change | REAL | NAV delta. | Derived |
| nav_return_pct | REAL | NAV return percentage. | Derived |
| source_file | TEXT | Raw file that contributed the row. | Cleaned NAV history |

## fact_aum
| Column | Type | Business Definition | Source |
| --- | --- | --- | --- |
| aum_key | INTEGER | Surrogate fact key. | Derived |
| fund_key | INTEGER | Links to dim_fund. | Cleaned NAV history |
| date_key | INTEGER | Latest observation date for the fund. | Cleaned NAV history |
| aum_value | REAL | NAV-derived AUM proxy because no raw AUM feed is present. | Derived |
| observation_count | INTEGER | Number of NAV observations used. | Derived |
| min_nav | REAL | Minimum observed NAV. | Derived |
| max_nav | REAL | Maximum observed NAV. | Derived |
| proxy_method | TEXT | Method used to approximate AUM. | Derived |
| source_file | TEXT | Originating summary file. | Derived |

## fact_transactions
Reserved for investor transaction sources when available.

## fact_performance
Reserved for scheme performance sources when available.
""".strip()


class MutualFundPipeline:
    """Small pipeline that keeps the processing readable and easy to follow."""

    def __init__(self) -> None:
        self.raw_dir = RAW_DIR
        self.processed_dir = PROCESSED_DIR
        self.db_path = DB_PATH

    @staticmethod
    def _read_meta(json_path: Path | None) -> dict:
        if not json_path or not json_path.exists():
            return {}
        with json_path.open(encoding="utf-8") as handle:
            return json.load(handle).get("meta", {})

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

    def clean_nav(self, path: Path) -> pd.DataFrame:
        """Clean one NAV CSV and return the standard shape used downstream."""
        df = pd.read_csv(path).rename(columns=str.lower)
        meta = self._read_meta(path.with_suffix(".json"))

        if "scheme_code" in df.columns:
            df = df.rename(columns={"scheme_code": "amfi_code"})

        df["amfi_code"] = pd.to_numeric(df["amfi_code"], errors="coerce").astype("Int64")
        df["date"] = self._parse_date(df["date"])
        df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
        df["source_file"] = path.name

        for column in [
            "scheme_name",
            "fund_house",
            "scheme_type",
            "scheme_category",
            "isin_growth",
            "isin_div_reinvestment",
        ]:
            if column not in df.columns:
                df[column] = meta.get(column, "")
            df[column] = df[column].map(self._clean_text)

        df = df.dropna(subset=["amfi_code", "date"])
        df = df.sort_values(["amfi_code", "date"])
        df = df.drop_duplicates(subset=["amfi_code", "date"], keep="last")
        df["nav"] = df.groupby("amfi_code")["nav"].ffill().bfill()
        df = df.loc[df["nav"].notna() & (df["nav"] > 0)].copy()

        df["previous_nav"] = df.groupby("amfi_code")["nav"].shift(1)
        df["nav_change"] = df["nav"] - df["previous_nav"]
        df["nav_return_pct"] = np.where(
            df["previous_nav"].notna() & (df["previous_nav"] != 0),
            ((df["nav"] - df["previous_nav"]) / df["previous_nav"]) * 100,
            np.nan,
        )

        return df[
            [
                "amfi_code",
                "date",
                "nav",
                "scheme_name",
                "fund_house",
                "scheme_type",
                "scheme_category",
                "isin_growth",
                "isin_div_reinvestment",
                "source_file",
                "previous_nav",
                "nav_change",
                "nav_return_pct",
            ]
        ].reset_index(drop=True)

    def build_frames(self, nav_history: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """Create the dimension and fact frames needed for SQLite."""
        dim_fund = (
            nav_history[
                [
                    "amfi_code",
                    "scheme_name",
                    "fund_house",
                    "scheme_type",
                    "scheme_category",
                    "isin_growth",
                    "isin_div_reinvestment",
                    "source_file",
                ]
            ]
            .drop_duplicates(subset=["amfi_code"])
            .sort_values(["fund_house", "scheme_name", "amfi_code"])
            .reset_index(drop=True)
        )
        dim_fund.insert(0, "fund_key", range(1, len(dim_fund) + 1))

        dim_date = pd.DataFrame(
            {"calendar_date": pd.date_range(nav_history["date"].min(), nav_history["date"].max(), freq="D")}
        )
        dim_date["date_key"] = dim_date["calendar_date"].dt.strftime("%Y%m%d").astype(int)
        dim_date["year"] = dim_date["calendar_date"].dt.year
        dim_date["quarter"] = dim_date["calendar_date"].dt.quarter
        dim_date["month"] = dim_date["calendar_date"].dt.month
        dim_date["month_name"] = dim_date["calendar_date"].dt.strftime("%B")
        dim_date["day"] = dim_date["calendar_date"].dt.day
        dim_date["day_name"] = dim_date["calendar_date"].dt.strftime("%A")
        dim_date["week_of_year"] = dim_date["calendar_date"].dt.isocalendar().week.astype(int)
        dim_date["is_weekend"] = dim_date["calendar_date"].dt.dayofweek.ge(5).astype(int)
        dim_date["is_month_start"] = dim_date["calendar_date"].dt.is_month_start.astype(int)
        dim_date["is_month_end"] = dim_date["calendar_date"].dt.is_month_end.astype(int)
        dim_date = dim_date[
            [
                "date_key",
                "calendar_date",
                "year",
                "quarter",
                "month",
                "month_name",
                "day",
                "day_name",
                "week_of_year",
                "is_weekend",
                "is_month_start",
                "is_month_end",
            ]
        ]

        fact_nav = nav_history.merge(dim_fund[["fund_key", "amfi_code"]], on="amfi_code", how="left")
        fact_nav["date_key"] = fact_nav["date"].dt.strftime("%Y%m%d").astype(int)
        fact_nav = fact_nav[
            ["fund_key", "date_key", "nav", "previous_nav", "nav_change", "nav_return_pct", "source_file"]
        ].copy()
        fact_nav.insert(0, "fact_nav_key", range(1, len(fact_nav) + 1))

        nav_summary = (
            nav_history.sort_values(["amfi_code", "date"])
            .groupby("amfi_code", as_index=False)
            .agg(
                latest_date=("date", "last"),
                observation_count=("nav", "size"),
                min_nav=("nav", "min"),
                max_nav=("nav", "max"),
                aum_value=("nav", "last"),
            )
        )
        fact_aum = nav_summary.merge(dim_fund[["fund_key", "amfi_code", "source_file"]], on="amfi_code", how="left")
        fact_aum["date_key"] = fact_aum["latest_date"].dt.strftime("%Y%m%d").astype(int)
        fact_aum["proxy_method"] = "latest_nav"
        fact_aum = fact_aum[
            ["fund_key", "date_key", "aum_value", "observation_count", "min_nav", "max_nav", "proxy_method", "source_file"]
        ].copy()
        fact_aum.insert(0, "aum_key", range(1, len(fact_aum) + 1))

        return {
            "dim_fund": dim_fund,
            "dim_date": dim_date,
            "fact_nav": fact_nav,
            "fact_aum": fact_aum,
        }

    def write_artifacts(self) -> None:
        SCHEMA_PATH.write_text(SCHEMA_SQL + "\n", encoding="utf-8")
        QUERIES_PATH.write_text(QUERIES_SQL + "\n", encoding="utf-8")
        DICTIONARY_PATH.write_text(DATA_DICTIONARY_MD + "\n", encoding="utf-8")

    def load_sqlite(self, frames: dict[str, pd.DataFrame]) -> None:
        if self.db_path.exists():
            self.db_path.unlink()

        engine = create_engine(f"sqlite:///{self.db_path.resolve().as_posix()}")

        with engine.begin() as connection:
            for statement in [stmt.strip() for stmt in SCHEMA_SQL.split(";") if stmt.strip()]:
                connection.exec_driver_sql(statement)

        for table_name in ["dim_fund", "dim_date", "fact_nav", "fact_aum"]:
            frames[table_name].to_sql(table_name, engine, if_exists="append", index=False)

        pd.DataFrame(
            columns=[
                "fund_key",
                "transaction_date_key",
                "investor_id",
                "transaction_type",
                "amount",
                "units",
                "nav",
                "state",
                "kyc_status",
                "source_file",
            ]
        ).to_sql("fact_transactions", engine, if_exists="append", index=False)

        pd.DataFrame(
            columns=[
                "fund_key",
                "date_key",
                "return_1m",
                "return_3m",
                "return_1y",
                "return_3y",
                "return_5y",
                "expense_ratio",
                "volatility",
                "sharpe_ratio",
                "anomaly_flag",
                "source_file",
            ]
        ).to_sql("fact_performance", engine, if_exists="append", index=False)

        expected_counts = {
            "dim_fund": len(frames["dim_fund"]),
            "dim_date": len(frames["dim_date"]),
            "fact_nav": len(frames["fact_nav"]),
            "fact_aum": len(frames["fact_aum"]),
            "fact_transactions": 0,
            "fact_performance": 0,
        }

        with engine.connect() as connection:
            for table_name, expected in expected_counts.items():
                actual = connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
                print(f"{table_name}: {actual}/{expected}")

    def run(self) -> None:
        nav_frames = []

        for csv_path in sorted(self.raw_dir.glob("nav_*.csv")):
            cleaned = self.clean_nav(csv_path)
            cleaned.to_csv(self.processed_dir / f"{csv_path.stem}_clean.csv", index=False)
            nav_frames.append(cleaned)

        nav_history = pd.concat(nav_frames, ignore_index=True)
        nav_history = nav_history.sort_values(["amfi_code", "date"]).reset_index(drop=True)
        nav_history.to_csv(self.processed_dir / "nav_history_clean.csv", index=False)

        frames = self.build_frames(nav_history)
        for table_name, frame in frames.items():
            frame.to_csv(self.processed_dir / f"{table_name}.csv", index=False)

        self.write_artifacts()
        self.load_sqlite(frames)


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pipeline = MutualFundPipeline()
    pipeline.run()


if __name__ == "__main__":
    main()