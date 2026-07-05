#!/usr/bin/env python
"""
recommender.py — Mutual Fund Recommendation Tool
==================================================
Recommends mutual funds based on risk appetite (Low / Moderate / High).
Retrieves fund performance from bluestock_mf.db, calculates Sharpe ratios,
and outputs recommendations in a structured table.

Usage:
    python recommender.py --risk High
    python recommender.py (interactive mode)
"""

import os
import sqlite3
import argparse
import numpy as np
import pandas as pd

from pathlib import Path

# Constants
SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR.parent / "data" / "db" / "bluestock_mf.db"
RF_DAILY = 0.065 / 252  # 6.5% annual risk-free rate proxy
N_DAYS = 252            # Annualisation factor

def get_risk_grade(category: str) -> str:
    """Map scheme category to risk grade."""
    category_lower = category.lower()
    if "debt" in category_lower or "money market" in category_lower or "treasury" in category_lower:
        return "Low"
    elif "large cap" in category_lower or "elss" in category_lower or "index" in category_lower:
        return "Moderate"
    elif "mid cap" in category_lower or "small cap" in category_lower or "sectoral" in category_lower:
        return "High"
    else:
        return "Unknown"

def load_data() -> pd.DataFrame:
    """Load fund NAV history, calculate Sharpe ratio, and map risk grade."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database file '{DB_PATH}' not found. Please ensure it is in the data/db directory.")
    
    conn = sqlite3.connect(str(DB_PATH))
    
    # Load funds and their categories
    funds = pd.read_sql_query("""
        SELECT fund_key, amfi_code, scheme_name, scheme_category, fund_house
        FROM dim_fund
    """, conn)
    
    # Load pre-computed performance metrics
    perf = pd.read_sql_query("""
        SELECT fund_key, sharpe_ratio 
        FROM fact_performance
        WHERE sharpe_ratio IS NOT NULL
    """, conn)
    
    # If pre-computed Sharpe ratios are not available, calculate dynamically
    if len(perf) > 0:
        sharpe_ratios = dict(zip(perf['fund_key'], perf['sharpe_ratio']))
        conn.close()
    else:
        # Load NAVs to compute daily returns
        nav_history = pd.read_sql_query("""
            SELECT fund_key, date_key, nav
            FROM fact_nav
            ORDER BY fund_key, date_key
        """, conn)
        conn.close()
        
        # Calculate daily returns per fund
        nav_history['date'] = pd.to_datetime(nav_history['date_key'].astype(str), format='%Y%m%d')
        nav_pivot = nav_history.pivot(index='date', columns='fund_key', values='nav').sort_index()
        returns = nav_pivot.pct_change().dropna(how='all')
        
        # Calculate Sharpe ratios
        sharpe_ratios = {}
        for fund_key in returns.columns:
            ret_series = returns[fund_key].dropna()
            if len(ret_series) > 10:
                excess_ret = ret_series - RF_DAILY
                std_dev = excess_ret.std()
                if std_dev > 0:
                    sharpe = (excess_ret.mean() / std_dev) * np.sqrt(N_DAYS)
                    sharpe_ratios[fund_key] = sharpe
                else:
                    sharpe_ratios[fund_key] = np.nan
            else:
                sharpe_ratios[fund_key] = np.nan
            
    # Map back to fund info
    funds['risk_grade'] = funds['scheme_category'].apply(get_risk_grade)
    funds['sharpe_ratio'] = funds['fund_key'].map(sharpe_ratios)
    
    return funds

def recommend(risk_appetite: str) -> None:
    """Recommend top 3 funds based on risk appetite."""
    risk_appetite = risk_appetite.strip().capitalize()
    if risk_appetite not in ["Low", "Moderate", "High"]:
        print(f"Error: Invalid risk appetite '{risk_appetite}'. Must be 'Low', 'Moderate', or 'High'.")
        return
        
    try:
        funds = load_data()
    except Exception as e:
        print(f"Error loading database: {e}")
        return
        
    # Filter by risk grade
    matched_funds = funds[funds['risk_grade'] == risk_appetite].copy()
    
    if matched_funds.empty:
        print(f"No funds found matching risk grade: {risk_appetite}")
        return
        
    # Sort by Sharpe Ratio (descending)
    recommended = matched_funds.sort_values('sharpe_ratio', ascending=False).head(3).reset_index(drop=True)
    
    # Format and print the table
    print(f"\n==========================================================================")
    print(f"               RECOMMENDED MUTUAL FUNDS FOR RISK APPETITE: {risk_appetite.upper()}")
    print(f"==========================================================================")
    
    header = f"{'Rank':<5} | {'Scheme Name':<60} | {'Sharpe Ratio':<12}"
    print(header)
    print("-" * len(header))
    
    for i, row in recommended.iterrows():
        sr_val = f"{row['sharpe_ratio']:.4f}" if not pd.isna(row['sharpe_ratio']) else "N/A"
        scheme_short = row['scheme_name']
        if len(scheme_short) > 60:
            scheme_short = scheme_short[:57] + "..."
        print(f"{i+1:<5} | {scheme_short:<60} | {sr_val:<12}")
        
    print("==========================================================================\n")

def main():
    parser = argparse.ArgumentParser(description="Recommend mutual funds by risk appetite.")
    parser.add_argument(
        "--risk", 
        type=str, 
        choices=["Low", "Moderate", "High", "low", "moderate", "high"],
        help="Investor risk appetite (Low / Moderate / High)"
    )
    args = parser.parse_args()
    
    if args.risk:
        recommend(args.risk)
    else:
        # Interactive mode
        print("Welcome to the Bluestock Mutual Fund Recommender Tool!")
        while True:
            try:
                risk_input = input("Enter your risk appetite (Low, Moderate, High) or 'exit' to quit: ").strip()
                if risk_input.lower() == 'exit':
                    print("Goodbye!")
                    break
                if risk_input.capitalize() in ["Low", "Moderate", "High"]:
                    recommend(risk_input)
                else:
                    print("Invalid input. Please choose from: Low, Moderate, High.")
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

if __name__ == "__main__":
    main()
