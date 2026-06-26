#!/usr/bin/env python
"""Mutual fund cleaning, star-schema build, and SQLite load pipeline."""

from __future__ import annotations

import json
import re
from pathlib import Path
from textwrap import dedent
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


VALID_TRANSACTION_TYPES = {
    "sip": "SIP",
    "systematic investment plan": "SIP",
    "systematicinvestmentplan": "SIP",
    "lumpsum": "Lumpsum",
    "lump sum": "Lumpsum",
    "lump-sum": "Lumpsum",
    "redemption": "Redemption",
    "redeem": "Redemption",
    "withdrawal": "Redemption",
}

VALID_KYC_STATUSES = {"verified", "pending", "rejected", "not_submitted"}
EXPENSE_RATIO_MIN = 0.1
EXPENSE_RATIO_MAX = 2.5


SCHEMA_SQL = dedent(
    """
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
    """
).strip()


QUERIES_SQL = dedent(
    """
    -- 1. Top 5 funds by AUM proxy
    SELECT f.scheme_name, f.fund_house, a.aum_value, a.observation_count, a.proxy_method
    FROM fact_aum AS a
    JOIN dim_fund AS f ON f.fund_key = a.fund_key
    ORDER BY a.aum_value DESC
    LIMIT 5;

    -- 2. Average NAV per month
    SELECT d.year, d.month, d.month_name, ROUND(AVG(n.nav), 4) AS average_nav
    FROM fact_nav AS n
    JOIN dim_date AS d ON d.date_key = n.date_key
    GROUP BY d.year, d.month, d.month_name
    ORDER BY d.year, d.month;

    -- 3. SIP YoY growth
    WITH sip_by_year AS (
        SELECT d.year, SUM(t.amount) AS sip_amount
        FROM fact_transactions AS t
        JOIN dim_date AS d ON d.date_key = t.transaction_date_key
        WHERE t.transaction_type = 'SIP'
        GROUP BY d.year
    )
    SELECT year, sip_amount,
           ROUND(100.0 * (sip_amount - LAG(sip_amount) OVER (ORDER BY year)) / NULLIF(LAG(sip_amount) OVER (ORDER BY year), 0), 2) AS yoy_growth_pct
    FROM sip_by_year
    ORDER BY year;

    -- 4. Transactions by state
    SELECT COALESCE(state, 'Unknown') AS state, COUNT(*) AS transaction_count, ROUND(SUM(amount), 2) AS total_amount
    FROM fact_transactions
    GROUP BY COALESCE(state, 'Unknown')
    ORDER BY transaction_count DESC, total_amount DESC;

    -- 5. Funds with expense_ratio below 1%
    SELECT f.scheme_name, f.fund_house, p.expense_ratio
    FROM fact_performance AS p
    JOIN dim_fund AS f ON f.fund_key = p.fund_key
    WHERE p.expense_ratio < 1.0
    ORDER BY p.expense_ratio ASC;

    -- 6. Highest NAV changes
    SELECT f.scheme_name, d.calendar_date, n.nav, n.previous_nav, (n.nav - n.previous_nav) AS nav_change
    FROM fact_nav AS n
    JOIN dim_fund AS f ON f.fund_key = n.fund_key
    JOIN dim_date AS d ON d.date_key = n.date_key
    WHERE n.previous_nav IS NOT NULL
    ORDER BY ABS(n.nav - n.previous_nav) DESC
    LIMIT 10;

    -- 7. Fund house average NAV trend
    SELECT f.fund_house, d.year, d.month, ROUND(AVG(n.nav), 4) AS average_nav
    FROM fact_nav AS n
    JOIN dim_fund AS f ON f.fund_key = n.fund_key
    JOIN dim_date AS d ON d.date_key = n.date_key
    GROUP BY f.fund_house, d.year, d.month
    ORDER BY f.fund_house, d.year, d.month;

    -- 8. Funds with the longest NAV history
    SELECT f.scheme_name, f.fund_house, COUNT(*) AS nav_observations, MIN(d.calendar_date) AS first_observation, MAX(d.calendar_date) AS latest_observation
    FROM fact_nav AS n
    JOIN dim_fund AS f ON f.fund_key = n.fund_key
    JOIN dim_date AS d ON d.date_key = n.date_key
    GROUP BY f.scheme_name, f.fund_house
    ORDER BY nav_observations DESC
    LIMIT 10;

    -- 9. Performance anomaly counts by fund
    SELECT f.scheme_name, COUNT(*) AS anomaly_rows
    FROM fact_performance AS p
    JOIN dim_fund AS f ON f.fund_key = p.fund_key
    WHERE p.anomaly_flag = 1
    GROUP BY f.scheme_name
    ORDER BY anomaly_rows DESC, f.scheme_name;

    -- 10. Month-end NAV trend
    SELECT f.scheme_name, d.calendar_date, n.nav
    FROM fact_nav AS n
    JOIN dim_fund AS f ON f.fund_key = n.fund_key
    JOIN dim_date AS d ON d.date_key = n.date_key
    WHERE d.is_month_end = 1
    ORDER BY f.scheme_name, d.calendar_date;
    """
).strip()


DATA_DICTIONARY_MD = dedent(
    """
    # Mutual Fund Data Dictionary

    ## Source Files
    - `data/raw/nav_*.csv`: NAV history extracts per scheme.
    - `data/raw/nav_*.json`: scheme metadata and NAV history payloads.
    - `reports/nav_fetch_summary.csv`: high-level NAV summary used for proxy AUM aggregation.

    ## nav_history_clean.csv
    | Column | Type | Business Definition | Source |
    | --- | --- | --- | --- |
    | amfi_code | INTEGER | Unique AMFI scheme identifier used as the natural fund key. | Raw CSV / JSON metadata |
    | date | DATE | NAV observation date. | Raw NAV CSV and JSON payload |
    | nav | REAL | Daily net asset value. | Raw NAV CSV / JSON payload |
    | scheme_name | TEXT | Human-readable fund name. | Raw CSV / JSON meta |
    | fund_house | TEXT | Asset management company name. | Raw CSV / JSON meta |
    | scheme_type | TEXT | Scheme family such as open-ended equity or debt. | Raw JSON meta |
    | scheme_category | TEXT | Category describing the fund objective. | Raw JSON meta |
    | isin_growth | TEXT | Growth option ISIN. | Raw JSON meta |
    | isin_div_reinvestment | TEXT | Dividend/reinvestment option ISIN. | Raw JSON meta |
    | source_file | TEXT | Originating raw file name. | File system |
    | previous_nav | REAL | Previous NAV for the same fund. | Derived |
    | nav_change | REAL | Day-over-day NAV change. | Derived |
    | nav_return_pct | REAL | Day-over-day NAV return percentage. | Derived |

    ## dim_fund
    | Column | Type | Business Definition | Source |
    | --- | --- | --- | --- |
    | fund_key | INTEGER | Surrogate primary key for the fund dimension. | Derived |
    | amfi_code | INTEGER | Natural fund key. | Cleaned NAV history |
    | scheme_name | TEXT | Fund name. | Cleaned NAV history |
    | fund_house | TEXT | AMC name. | Cleaned NAV history |
    | scheme_type | TEXT | Scheme family. | Raw JSON meta |
    | scheme_category | TEXT | Fund category. | Raw JSON meta |
    | isin_growth | TEXT | Growth ISIN. | Raw JSON meta |
    | isin_div_reinvestment | TEXT | Dividend/reinvestment ISIN. | Raw JSON meta |
    | source_file | TEXT | File contributing the dimension row. | Cleaned NAV history |
    | created_at | TEXT | Row creation timestamp. | SQLite default |

    ## dim_date
    | Column | Type | Business Definition | Source |
    | --- | --- | --- | --- |
    | date_key | INTEGER | Surrogate date key in YYYYMMDD format. | Derived |
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
    | source_file | TEXT | Raw file that contributed the fact row. | Cleaned NAV history |

    ## fact_aum
    | Column | Type | Business Definition | Source |
    | --- | --- | --- | --- |
    | aum_key | INTEGER | Surrogate fact key. | Derived |
    | fund_key | INTEGER | Links to dim_fund. | Cleaned NAV history |
    | date_key | INTEGER | Latest observation date for the fund. | Cleaned NAV history |
    | aum_value | REAL | NAV-derived AUM proxy because no raw AUM feed is present. | Derived from NAV summary |
    | observation_count | INTEGER | Number of NAV observations used to compute the proxy. | Derived |
    | min_nav | REAL | Minimum observed NAV. | Derived |
    | max_nav | REAL | Maximum observed NAV. | Derived |
    | proxy_method | TEXT | Method used to approximate AUM. | Derived |
    | source_file | TEXT | Originating summary file. | Derived |

    ## fact_transactions
    Intended for investor transaction sources when those CSVs are added to the workspace.

    ## fact_performance
    Intended for scheme performance sources when those CSVs are added to the workspace.
    """
).strip()


class MutualFundPipeline:
    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or Path(__file__).resolve().parents[1]
        self.raw_dir = self.root_dir / "data" / "raw"
        self.processed_dir = self.root_dir / "data" / "processed"
        self.reports_dir = self.root_dir / "reports"
        self.db_path = self.root_dir / "bluestock_mf.db"
        self.schema_path = self.root_dir / "schema.sql"
        self.queries_path = self.root_dir / "queries.sql"
        self.dictionary_path = self.root_dir / "data_dictionary.md"

        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.cleaning_log: list[dict[str, object]] = []

    @staticmethod
    def _read_json_metadata(json_path: Path) -> dict:
        if not json_path.exists():
            return {}
        with json_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _safe_date(series: pd.Series) -> pd.Series:
        parsed = pd.to_datetime(series, errors="coerce")
        if parsed.notna().any():
            return parsed
        return pd.to_datetime(series, errors="coerce", dayfirst=True)

    @staticmethod
    def _normalize_value(value: object) -> str:
        if pd.isna(value):
            return ""
        return re.sub(r"\s+", " ", str(value)).strip()

    @staticmethod
    def _normalize_kyc_status(value: object) -> str:
        normalized = re.sub(r"[\s\-]+", "_", str(value).strip().lower())
        return normalized if normalized in VALID_KYC_STATUSES else "pending"

    @staticmethod
    def _standardize_transaction_type(value: object) -> str:
        normalized = re.sub(r"[\s\-]+", " ", str(value).strip().lower())
        compact = normalized.replace(" ", "")
        if normalized in VALID_TRANSACTION_TYPES:
            return VALID_TRANSACTION_TYPES[normalized]
        if compact in VALID_TRANSACTION_TYPES:
            return VALID_TRANSACTION_TYPES[compact]
        return "Unknown"

    def discover_nav_sources(self) -> list[tuple[Path, Path | None]]:
        nav_files = sorted(self.raw_dir.glob("nav_*.csv"))
        sources: list[tuple[Path, Path | None]] = []
        for csv_path in nav_files:
            json_path = csv_path.with_suffix(".json")
            sources.append((csv_path, json_path if json_path.exists() else None))
        return sources

    def clean_nav_history(self, frame: pd.DataFrame, metadata: dict | None = None, source_file: str | None = None) -> pd.DataFrame:
        cleaned = frame.copy()
        cleaned.columns = [column.strip().lower() for column in cleaned.columns]

        if "scheme_code" in cleaned.columns and "amfi_code" not in cleaned.columns:
            cleaned = cleaned.rename(columns={"scheme_code": "amfi_code"})

        if "date" in cleaned.columns:
            cleaned["date"] = self._safe_date(cleaned["date"])
        if "nav" in cleaned.columns:
            cleaned["nav"] = pd.to_numeric(cleaned["nav"], errors="coerce")
        if "amfi_code" in cleaned.columns:
            cleaned["amfi_code"] = pd.to_numeric(cleaned["amfi_code"], errors="coerce").astype("Int64")

        meta = metadata or {}
        for column, value in {
            "scheme_name": meta.get("scheme_name", ""),
            "fund_house": meta.get("fund_house", ""),
            "scheme_type": meta.get("scheme_type", ""),
            "scheme_category": meta.get("scheme_category", ""),
            "isin_growth": meta.get("isin_growth", ""),
            "isin_div_reinvestment": meta.get("isin_div_reinvestment", ""),
        }.items():
            if column not in cleaned.columns:
                cleaned[column] = value

        if source_file is not None:
            cleaned["source_file"] = source_file

        for column in ["scheme_name", "fund_house", "scheme_type", "scheme_category", "isin_growth", "isin_div_reinvestment"]:
            if column in cleaned.columns:
                cleaned[column] = cleaned[column].map(self._normalize_value)

        cleaned = cleaned.dropna(subset=["amfi_code", "date"])
        cleaned = cleaned.sort_values(["amfi_code", "date"])
        cleaned = cleaned.drop_duplicates(subset=["amfi_code", "date"], keep="last")

        if "nav" in cleaned.columns:
            cleaned["nav"] = cleaned.groupby("amfi_code")["nav"].ffill().bfill()
            cleaned = cleaned.loc[cleaned["nav"].notna() & (cleaned["nav"] > 0)].copy()

        cleaned["previous_nav"] = cleaned.groupby("amfi_code")["nav"].shift(1)
        cleaned["nav_change"] = cleaned["nav"] - cleaned["previous_nav"]
        cleaned["nav_return_pct"] = np.where(
            cleaned["previous_nav"].notna() & (cleaned["previous_nav"] != 0),
            ((cleaned["nav"] - cleaned["previous_nav"]) / cleaned["previous_nav"]) * 100,
            np.nan,
        )

        cleaned = cleaned[[
            "amfi_code", "date", "nav", "scheme_name", "fund_house", "scheme_type",
            "scheme_category", "isin_growth", "isin_div_reinvestment", "source_file",
            "previous_nav", "nav_change", "nav_return_pct",
        ]]

        return cleaned.reset_index(drop=True)

    def clean_investor_transactions(self, frame: pd.DataFrame, source_file: str | None = None) -> pd.DataFrame:
        cleaned = frame.copy()
        cleaned.columns = [column.strip().lower() for column in cleaned.columns]

        if "transaction_date" not in cleaned.columns and "date" in cleaned.columns:
            cleaned = cleaned.rename(columns={"date": "transaction_date"})
        if "transaction_date" in cleaned.columns:
            cleaned["transaction_date"] = self._safe_date(cleaned["transaction_date"])
        if "transaction_type" in cleaned.columns:
            cleaned["transaction_type"] = cleaned["transaction_type"].map(self._standardize_transaction_type)
        if "amount" in cleaned.columns:
            cleaned["amount"] = pd.to_numeric(cleaned["amount"], errors="coerce")
            cleaned = cleaned.loc[cleaned["amount"] > 0].copy()
        if "kyc_status" in cleaned.columns:
            cleaned["kyc_status"] = cleaned["kyc_status"].map(self._normalize_kyc_status)
        if "state" in cleaned.columns:
            cleaned["state"] = cleaned["state"].map(self._normalize_value)
        if source_file is not None:
            cleaned["source_file"] = source_file
        return cleaned.drop_duplicates().reset_index(drop=True)

    def clean_scheme_performance(self, frame: pd.DataFrame, source_file: str | None = None) -> pd.DataFrame:
        cleaned = frame.copy()
        cleaned.columns = [column.strip().lower() for column in cleaned.columns]

        anomaly_mask = pd.Series(False, index=cleaned.index)
        return_columns = [column for column in cleaned.columns if "return" in column or column.endswith("cagr")]
        for column in return_columns:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
            anomaly_mask = anomaly_mask | (cleaned[column].notna() & (cleaned[column].abs() > 100))

        if "expense_ratio" in cleaned.columns:
            cleaned["expense_ratio"] = pd.to_numeric(cleaned["expense_ratio"], errors="coerce")
            anomaly_mask = anomaly_mask | (
                cleaned["expense_ratio"].notna()
                & ((cleaned["expense_ratio"] < EXPENSE_RATIO_MIN) | (cleaned["expense_ratio"] > EXPENSE_RATIO_MAX))
            )
            cleaned["expense_ratio"] = cleaned["expense_ratio"].clip(EXPENSE_RATIO_MIN, EXPENSE_RATIO_MAX)

        if source_file is not None:
            cleaned["source_file"] = source_file
        cleaned["anomaly_flag"] = anomaly_mask.astype(int)
        return cleaned.drop_duplicates().reset_index(drop=True)

    def build_star_schema_frames(self, nav_history: pd.DataFrame) -> dict[str, pd.DataFrame]:
        dim_fund = nav_history[[
            "amfi_code", "scheme_name", "fund_house", "scheme_type", "scheme_category",
            "isin_growth", "isin_div_reinvestment", "source_file",
        ]].drop_duplicates(subset=["amfi_code"]).copy()
        dim_fund = dim_fund.sort_values(["fund_house", "scheme_name", "amfi_code"]).reset_index(drop=True)
        dim_fund.insert(0, "fund_key", range(1, len(dim_fund) + 1))

        date_range = pd.date_range(nav_history["date"].min(), nav_history["date"].max(), freq="D")
        dim_date = pd.DataFrame({"calendar_date": date_range})
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
        dim_date = dim_date[[
            "date_key", "calendar_date", "year", "quarter", "month", "month_name",
            "day", "day_name", "week_of_year", "is_weekend", "is_month_start", "is_month_end",
        ]]

        fact_nav = nav_history.merge(dim_fund[["fund_key", "amfi_code"]], on="amfi_code", how="left")
        fact_nav["date_key"] = fact_nav["date"].dt.strftime("%Y%m%d").astype(int)
        fact_nav = fact_nav[["fund_key", "date_key", "nav", "previous_nav", "nav_change", "nav_return_pct", "source_file"]].copy()
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
        fact_aum = fact_aum[["fund_key", "date_key", "aum_value", "observation_count", "min_nav", "max_nav", "proxy_method", "source_file"]].copy()
        fact_aum.insert(0, "aum_key", range(1, len(fact_aum) + 1))

        return {"dim_fund": dim_fund, "dim_date": dim_date, "fact_nav": fact_nav, "fact_aum": fact_aum}

    def write_artifacts(self) -> None:
        self.schema_path.write_text(SCHEMA_SQL + "\n", encoding="utf-8")
        self.queries_path.write_text(QUERIES_SQL + "\n", encoding="utf-8")
        self.dictionary_path.write_text(DATA_DICTIONARY_MD + "\n", encoding="utf-8")

    def _sqlite_engine(self):
        absolute_path = self.db_path.resolve().as_posix()
        return create_engine(f"sqlite:///{absolute_path}")

    def _initialize_database(self, engine) -> None:
        with engine.begin() as connection:
            for statement in [stmt.strip() for stmt in SCHEMA_SQL.split(";") if stmt.strip()]:
                connection.exec_driver_sql(statement)

    def _load_table(self, engine, table_name: str, frame: pd.DataFrame) -> None:
        frame.to_sql(table_name, engine, if_exists="append", index=False)

    def _verify_row_counts(self, engine, expected_counts: dict[str, int]) -> None:
        with engine.connect() as connection:
            for table_name, expected_count in expected_counts.items():
                actual_count = connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
                status = "OK" if actual_count == expected_count else "MISMATCH"
                print(f"   {table_name}: expected {expected_count:,}, actual {actual_count:,} [{status}]")

    def run(self) -> None:
        print("Cleaning mutual fund data")
        print("=" * 72)

        nav_sources = self.discover_nav_sources()
        if not nav_sources:
            print("No raw NAV CSV files found in data/raw/")
            return

        cleaned_nav_frames: list[pd.DataFrame] = []

        for csv_path, json_path in nav_sources:
            raw_frame = pd.read_csv(csv_path)
            metadata = self._read_json_metadata(json_path) if json_path is not None else {}
            cleaned_frame = self.clean_nav_history(raw_frame, metadata=metadata.get("meta", metadata), source_file=csv_path.name)
            output_path = self.processed_dir / f"{csv_path.stem}_clean.csv"
            cleaned_frame.to_csv(output_path, index=False)
            cleaned_nav_frames.append(cleaned_frame)
            self.cleaning_log.append({"dataset": csv_path.stem, "rows": len(cleaned_frame)})
            print(f"   cleaned {csv_path.name} -> {output_path.name} ({len(cleaned_frame):,} rows)")

        nav_history = pd.concat(cleaned_nav_frames, ignore_index=True).sort_values(["amfi_code", "date"]).reset_index(drop=True)
        nav_history_output = self.processed_dir / "nav_history_clean.csv"
        nav_history.to_csv(nav_history_output, index=False)

        star_frames = self.build_star_schema_frames(nav_history)
        for table_name, frame in star_frames.items():
            frame.to_csv(self.processed_dir / f"{table_name}.csv", index=False)

        self.write_artifacts()

        if self.db_path.exists():
            self.db_path.unlink()

        engine = self._sqlite_engine()
        self._initialize_database(engine)
        self._load_table(engine, "dim_fund", star_frames["dim_fund"])
        self._load_table(engine, "dim_date", star_frames["dim_date"])
        self._load_table(engine, "fact_nav", star_frames["fact_nav"])
        self._load_table(engine, "fact_aum", star_frames["fact_aum"])
        self._load_table(engine, "fact_transactions", pd.DataFrame(columns=["fund_key", "transaction_date_key", "investor_id", "transaction_type", "amount", "units", "nav", "state", "kyc_status", "source_file"]))
        self._load_table(engine, "fact_performance", pd.DataFrame(columns=["fund_key", "date_key", "return_1m", "return_3m", "return_1y", "return_3y", "return_5y", "expense_ratio", "volatility", "sharpe_ratio", "anomaly_flag", "source_file"]))

        print("\nRow count verification")
        print("-" * 72)
        self._verify_row_counts(engine, {
            "dim_fund": len(star_frames["dim_fund"]),
            "dim_date": len(star_frames["dim_date"]),
            "fact_nav": len(star_frames["fact_nav"]),
            "fact_aum": len(star_frames["fact_aum"]),
            "fact_transactions": 0,
            "fact_performance": 0,
        })

        print("\nArtifacts written")
        print("-" * 72)
        for artifact in [nav_history_output, self.schema_path, self.queries_path, self.dictionary_path, self.db_path]:
            print(f"   {artifact.relative_to(self.root_dir)}")


def main() -> None:
    pipeline = MutualFundPipeline()
    pipeline.run()


if __name__ == "__main__":
    main()