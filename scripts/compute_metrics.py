#!/usr/bin/env python
"""
compute_metrics.py — Fund Performance Analytics Engine
=======================================================
Computes all performance metrics for every fund in bluestock_mf.db:
  • Returns   : 1-month, 3-month, 1Y/3Y/5Y CAGR
  • Risk       : Volatility (annualised), Sharpe Ratio, Sortino Ratio
  • Benchmark  : Alpha & Beta vs Nifty 50 (OLS regression)
  • Drawdown   : Maximum Drawdown (date range + magnitude)
  • Scorecard  : Composite 0–100 ranking across all metrics
  • Exports    : Saves CSVs to reports/ and updates fact_performance in DB

Usage:
    python scripts/compute_metrics.py
"""

import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT       = SCRIPT_DIR.parent
DB_PATH    = ROOT / "data" / "db" / "bluestock_mf.db"
REPORTS    = ROOT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

RF_DAILY = 0.065 / 252   # 6.5% annual risk-free rate (RBI repo rate proxy)
N_DAYS   = 252            # Annualisation factor (trading days/year)


# ── Helpers ───────────────────────────────────────────────────────────────────

def cagr(nav_series: pd.Series, n_years: float) -> float:
    """CAGR = (end/start)^(1/n) - 1, using trading-day count."""
    n_td = int(n_years * N_DAYS)
    if len(nav_series) < n_td + 1:
        return np.nan
    return ((nav_series.iloc[-1] / nav_series.iloc[-(n_td + 1)]) ** (1 / n_years) - 1) * 100


def sharpe(ret: pd.Series) -> float:
    """Sharpe = (mean(excess) / std(excess)) * sqrt(252)."""
    if len(ret) < 2:
        return np.nan
    exc = ret - RF_DAILY
    sd  = exc.std()
    return float((exc.mean() / sd) * np.sqrt(N_DAYS)) if sd > 0 else np.nan


def sortino(ret: pd.Series) -> float:
    """Sortino = (mean(excess) / downside_std) * sqrt(252)."""
    if len(ret) < 2:
        return np.nan
    exc      = ret - RF_DAILY
    downside = exc[exc < 0]
    if len(downside) < 2:
        return np.nan
    ds_std = downside.std()
    return float((exc.mean() / ds_std) * np.sqrt(N_DAYS)) if ds_std > 0 else np.nan


def max_drawdown(nav_series: pd.Series) -> tuple[float, str, str]:
    """
    Maximum Drawdown = min(nav / running_max - 1).
    Returns (mdd_pct, start_date_str, end_date_str).
    """
    roll_max  = nav_series.cummax()
    drawdowns = (nav_series / roll_max) - 1
    mdd_val   = float(drawdowns.min()) * 100           # as percentage

    end_idx   = drawdowns.idxmin()
    # Walk back to find the peak before this trough
    peak_idx  = roll_max[:end_idx].idxmax()

    start_str = str(peak_idx.date()) if hasattr(peak_idx, "date") else str(peak_idx)
    end_str   = str(end_idx.date())  if hasattr(end_idx,  "date") else str(end_idx)
    return mdd_val, start_str, end_str


def alpha_beta(fund_ret: pd.Series, bench_ret: pd.Series) -> tuple[float, float, float]:
    """
    OLS regression of fund returns on benchmark returns.
    Returns (alpha_annualised, beta, r_squared).
    Alpha = intercept * 252  (annualised).
    """
    aligned = pd.concat([fund_ret, bench_ret], axis=1).dropna()
    if len(aligned) < 30:
        return np.nan, np.nan, np.nan
    slope, intercept, r, _, _ = stats.linregress(
        aligned.iloc[:, 1].values,
        aligned.iloc[:, 0].values
    )
    alpha_ann = intercept * N_DAYS * 100   # convert to %
    return round(float(alpha_ann), 4), round(float(slope), 4), round(float(r ** 2), 4)


def rank_score(series: pd.Series, ascending: bool = True) -> pd.Series:
    """Rank a series 0–100 (100 = best)."""
    r = series.rank(method="average", ascending=ascending)
    n = series.notna().sum()
    return ((r - 1) / max(n - 1, 1) * 100).round(2)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(str(DB_PATH))

    # ── Load NAV data ──────────────────────────────────────────────────────────
    raw = pd.read_sql_query("""
        SELECT f.fund_key, f.scheme_name, f.scheme_category, d.calendar_date, n.nav
        FROM fact_nav n
        JOIN dim_fund f ON f.fund_key  = n.fund_key
        JOIN dim_date d ON d.date_key  = n.date_key
        ORDER BY f.fund_key, d.calendar_date
    """, conn, parse_dates=["calendar_date"])

    funds = pd.read_sql_query(
        "SELECT fund_key, amfi_code, scheme_name, scheme_category FROM dim_fund", conn
    )

    # ── Load Nifty50 benchmark ─────────────────────────────────────────────────
    nifty = pd.read_sql_query("""
        SELECT d.calendar_date, n.nifty_close
        FROM fact_nifty50 n
        JOIN dim_date d ON d.date_key = n.date_key
        ORDER BY d.calendar_date
    """, conn, parse_dates=["calendar_date"])
    nifty = nifty.set_index("calendar_date")["nifty_close"].sort_index()
    nifty_ret = nifty.pct_change().dropna()

    latest_date_key = int(
        pd.read_sql_query("SELECT MAX(date_key) FROM fact_nav", conn).iloc[0, 0]
    )

    # ── Pivot NAV by fund ──────────────────────────────────────────────────────
    nav_pivot = raw.pivot(index="calendar_date", columns="fund_key", values="nav").sort_index()
    returns   = nav_pivot.pct_change().dropna(how="all")

    # ── Compute metrics per fund ───────────────────────────────────────────────
    perf_rows  = []
    ab_rows    = []
    mdd_rows   = []
    sc_rows    = []

    for _, fund in funds.iterrows():
        fk   = int(fund["fund_key"])
        name = fund["scheme_name"]

        if fk not in nav_pivot.columns:
            continue

        f_nav = nav_pivot[fk].dropna()
        f_ret = returns[fk].dropna() if fk in returns.columns else pd.Series(dtype=float)

        if len(f_nav) < 2:
            continue

        # Returns
        r_1m = (f_nav.iloc[-1] / f_nav.iloc[-22]  - 1) * 100 if len(f_nav) >= 22  else np.nan
        r_3m = (f_nav.iloc[-1] / f_nav.iloc[-64]  - 1) * 100 if len(f_nav) >= 64  else np.nan
        r_1y = cagr(f_nav, 1)
        r_3y = cagr(f_nav, 3)
        r_5y = cagr(f_nav, 5)

        # Risk
        vol     = float(f_ret.std() * np.sqrt(N_DAYS) * 100) if len(f_ret) > 1 else np.nan
        sh      = sharpe(f_ret)
        so      = sortino(f_ret)

        # Drawdown
        mdd_val, mdd_start, mdd_end = max_drawdown(f_nav) if len(f_nav) >= 2 else (np.nan, "", "")

        # Alpha / Beta vs Nifty50
        alp, bet, r2 = alpha_beta(f_ret, nifty_ret)

        # Anomaly flag: any daily return > 8%
        has_anomaly = int((f_ret.abs() > 0.08).any()) if len(f_ret) > 0 else 0

        perf_rows.append({
            "fund_key":     fk,
            "date_key":     latest_date_key,
            "return_1m":    round(float(r_1m), 4) if not np.isnan(r_1m) else None,
            "return_3m":    round(float(r_3m), 4) if not np.isnan(r_3m) else None,
            "return_1y":    round(float(r_1y), 4) if not np.isnan(r_1y) else None,
            "return_3y":    round(float(r_3y), 4) if not np.isnan(r_3y) else None,
            "return_5y":    round(float(r_5y), 4) if not np.isnan(r_5y) else None,
            "expense_ratio": 1.0,
            "volatility":   round(vol, 4) if not np.isnan(vol) else None,
            "sharpe_ratio": round(sh, 4)  if not np.isnan(sh)  else None,
            "anomaly_flag": has_anomaly,
            "source_file":  "performance_analytics",
        })

        ab_rows.append({
            "scheme_name":  name,
            "alpha_annual": alp,
            "beta":         bet,
            "r_squared":    r2,
        })

        mdd_rows.append({
            "scheme_name":   name,
            "max_drawdown_pct": round(mdd_val, 4) if not np.isnan(mdd_val) else None,
            "drawdown_start": mdd_start,
            "drawdown_end":   mdd_end,
        })

        sc_rows.append({
            "fund_key":     fk,
            "scheme_name":  name,
            "return_3y":    r_3y,
            "sharpe_ratio": sh,
            "alpha":        alp,
            "expense_ratio": 1.0,
            "max_drawdown": mdd_val,
            "sortino_ratio": so,
            "volatility":   vol,
        })

    perf_df = pd.DataFrame(perf_rows)
    ab_df   = pd.DataFrame(ab_rows)
    mdd_df  = pd.DataFrame(mdd_rows)
    sc_df   = pd.DataFrame(sc_rows)

    # ── Update fact_performance in DB ─────────────────────────────────────────
    conn.execute("DELETE FROM fact_performance")
    perf_df.to_sql("fact_performance", conn, if_exists="append", index=False)
    conn.commit()

    # ── Fund Scorecard (0–100 composite) ──────────────────────────────────────
    # 30% × 3Y return rank  +  25% × Sharpe rank  +  20% × Alpha rank
    # 15% × Expense ratio rank (inverse — lower is better)
    # 10% × Max DD rank (inverse — less negative is better)
    sc = sc_df.copy()
    sc["r3y_rank"]    = rank_score(sc["return_3y"],     ascending=True)
    sc["sharpe_rank"] = rank_score(sc["sharpe_ratio"],  ascending=True)
    sc["alpha_rank"]  = rank_score(sc["alpha"],         ascending=True)
    sc["er_rank"]     = rank_score(-sc["expense_ratio"],ascending=True)  # lower expense = better
    sc["mdd_rank"]    = rank_score(-sc["max_drawdown"],  ascending=True)  # less negative = better

    sc["composite_score"] = (
        sc["r3y_rank"]    * 0.30 +
        sc["sharpe_rank"] * 0.25 +
        sc["alpha_rank"]  * 0.20 +
        sc["er_rank"]     * 0.15 +
        sc["mdd_rank"]    * 0.10
    ).round(2)

    scorecard_export = sc[[
        "scheme_name", "return_3y", "sharpe_ratio", "sortino_ratio",
        "alpha", "volatility", "max_drawdown", "expense_ratio", "composite_score"
    ]].sort_values("composite_score", ascending=False).reset_index(drop=True)
    scorecard_export.index += 1
    scorecard_export.index.name = "rank"

    # ── Sortino ratios CSV ────────────────────────────────────────────────────
    sortino_rows = []
    for _, fund in funds.iterrows():
        fk   = int(fund["fund_key"])
        name = fund["scheme_name"]
        if fk not in returns.columns:
            continue
        f_ret = returns[fk].dropna()
        so    = sortino(f_ret)
        sortino_rows.append({"scheme_name": name, "sortino_ratio": round(so, 4) if not np.isnan(so) else None})
    sortino_df = pd.DataFrame(sortino_rows)

    # ── CAGR comparison table ─────────────────────────────────────────────────
    cagr_rows = []
    for _, fund in funds.iterrows():
        fk   = int(fund["fund_key"])
        name = fund["scheme_name"]
        if fk not in nav_pivot.columns:
            continue
        f_nav = nav_pivot[fk].dropna()
        cagr_rows.append({
            "scheme_name": name,
            "cagr_1y":  round(cagr(f_nav, 1), 4)  if not np.isnan(cagr(f_nav, 1))  else None,
            "cagr_3y":  round(cagr(f_nav, 3), 4)  if not np.isnan(cagr(f_nav, 3))  else None,
            "cagr_5y":  round(cagr(f_nav, 5), 4)  if not np.isnan(cagr(f_nav, 5))  else None,
        })
    cagr_df = pd.DataFrame(cagr_rows)

    # ── Save all CSVs ─────────────────────────────────────────────────────────
    ab_df.to_csv(REPORTS / "alpha_beta.csv", index=False)
    mdd_df.to_csv(REPORTS / "max_drawdown.csv", index=False)
    scorecard_export.to_csv(REPORTS / "fund_scorecard.csv")
    sortino_df.to_csv(REPORTS / "sortino_ratios.csv", index=False)
    cagr_df.to_csv(REPORTS / "cagr_comparison.csv", index=False)

    # ── Sharpe ratios CSV ─────────────────────────────────────────────────────
    sharpe_rows = []
    for _, fund in funds.iterrows():
        fk   = int(fund["fund_key"])
        name = fund["scheme_name"]
        if fk not in returns.columns:
            continue
        f_ret = returns[fk].dropna()
        sh    = sharpe(f_ret)
        sharpe_rows.append({"scheme_name": name, "sharpe_ratio": round(sh, 4) if not np.isnan(sh) else None})
    pd.DataFrame(sharpe_rows).to_csv(REPORTS / "sharpe_ratios.csv", index=False)

    conn.close()

    # ── Print summary ─────────────────────────────────────────────────────────
    print("\nPerformance Metrics:")
    print(perf_df.to_string(index=False))

    print("\n\nAlpha & Beta vs Nifty50:")
    print(ab_df.to_string(index=False))

    print("\n\nMaximum Drawdown:")
    print(mdd_df.to_string(index=False))

    print("\n\nSortino Ratios:")
    print(sortino_df.to_string(index=False))

    print("\n\nFund Scorecard (0–100 composite):")
    print(scorecard_export.to_string())

    print(f"\n[DONE] Reports saved to: {REPORTS}")


if __name__ == "__main__":
    main()
