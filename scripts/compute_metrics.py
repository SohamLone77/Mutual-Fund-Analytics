#!/usr/bin/env python
"""
compute_metrics.py — Compute Fund Performance Metrics
======================================================
Computes 1m, 3m returns, 1y, 3y, 5y CAGR, volatility, and Sharpe ratios
for all schemes and saves them to the fact_performance table in SQLite.

Usage:
    python scripts/compute_metrics.py
"""

import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR.parent / "data" / "db" / "bluestock_mf.db"
RF_DAILY = 0.065 / 252  # 6.5% annual risk-free rate proxy
N_DAYS = 252            # Trading days per year

def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")
        
    conn = sqlite3.connect(str(DB_PATH))
    
    # Load raw NAV data
    raw = pd.read_sql_query("""
        SELECT f.fund_key, f.amfi_code, f.scheme_name, d.calendar_date, n.nav
        FROM fact_nav n
        JOIN dim_fund f ON f.fund_key = n.fund_key
        JOIN dim_date d ON d.date_key = n.date_key
        ORDER BY f.fund_key, d.calendar_date
    """, conn, parse_dates=["calendar_date"])
    
    # Load dim_fund keys
    funds = pd.read_sql_query("SELECT fund_key, amfi_code, scheme_name FROM dim_fund", conn)
    
    # Pivot NAVs
    nav = raw.pivot(index="calendar_date", columns="fund_key", values="nav").sort_index()
    returns = nav.pct_change().dropna(how="all")
    
    # Target date key (latest observation date)
    latest_date_key = int(pd.read_sql_query("SELECT MAX(date_key) FROM fact_nav", conn).iloc[0, 0])
    
    # Truncate/delete existing rows in fact_performance
    conn.execute("DELETE FROM fact_performance")
    
    performance_rows = []
    
    for _, fund in funds.iterrows():
        f_key = int(fund["fund_key"])
        f_nav = nav[f_key].dropna()
        f_ret = returns[f_key].dropna()
        
        if len(f_nav) < 2:
            continue
            
        # 1. 1-Month Return (last 21 trading days)
        r_1m = (f_nav.iloc[-1] / f_nav.iloc[-22] - 1) * 100 if len(f_nav) >= 22 else np.nan
        
        # 2. 3-Month Return (last 63 trading days)
        r_3m = (f_nav.iloc[-1] / f_nav.iloc[-64] - 1) * 100 if len(f_nav) >= 64 else np.nan
        
        # 3. 1-Year CAGR (252 trading days)
        r_1y = ((f_nav.iloc[-1] / f_nav.iloc[-253]) ** (252 / 252) - 1) * 100 if len(f_nav) >= 253 else np.nan
        
        # 4. 3-Year CAGR (756 trading days)
        r_3y = ((f_nav.iloc[-1] / f_nav.iloc[-757]) ** (252 / 756) - 1) * 100 if len(f_nav) >= 757 else np.nan
        
        # 5. 5-Year CAGR (1260 trading days)
        r_5y = ((f_nav.iloc[-1] / f_nav.iloc[-1261]) ** (252 / 1260) - 1) * 100 if len(f_nav) >= 1261 else np.nan
        
        # 6. Volatility (Annualised daily std)
        vol = f_ret.std() * np.sqrt(N_DAYS) * 100 if len(f_ret) > 1 else np.nan
        
        # 7. Sharpe Ratio
        if len(f_ret) > 1:
            excess_ret = f_ret - RF_DAILY
            std_dev = excess_ret.std()
            sharpe = (excess_ret.mean() / std_dev) * np.sqrt(N_DAYS) if std_dev > 0 else np.nan
        else:
            sharpe = np.nan
            
        # Anomaly flag (e.g. daily return exceeds +/- 8% as potential split/error)
        has_anomaly = 1 if ((f_ret.abs() > 0.08).any()) else 0
        
        performance_rows.append({
            "fund_key": f_key,
            "date_key": latest_date_key,
            "return_1m": round(float(r_1m), 4) if not pd.isna(r_1m) else None,
            "return_3m": round(float(r_3m), 4) if not pd.isna(r_3m) else None,
            "return_1y": round(float(r_1y), 4) if not pd.isna(r_1y) else None,
            "return_3y": round(float(r_3y), 4) if not pd.isna(r_3y) else None,
            "return_5y": round(float(r_5y), 4) if not pd.isna(r_5y) else None,
            "expense_ratio": 1.0,  # Direct plan proxy
            "volatility": round(float(vol), 4) if not pd.isna(vol) else None,
            "sharpe_ratio": round(float(sharpe), 4) if not pd.isna(sharpe) else None,
            "anomaly_flag": has_anomaly,
            "source_file": "performance_analytics"
        })
        
    perf_df = pd.DataFrame(performance_rows)
    perf_df.to_sql("fact_performance", conn, if_exists="append", index=False)
    conn.commit()
    
    print("\nCalculated and loaded performance metrics:")
    print(perf_df.to_string(index=False))
    
    conn.close()

if __name__ == "__main__":
    main()
