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
