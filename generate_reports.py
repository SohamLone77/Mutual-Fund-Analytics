"""
generate_reports.py — Regenerates all CSV and chart reports from the live SQLite DB.
Run this after any ETL or metric recomputation to keep reports/ up to date.
"""

import sqlite3
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "db" / "bluestock_mf.db"
REPORTS = BASE / "reports"
REPORTS.mkdir(exist_ok=True)

print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Connecting to DB: {DB_PATH}")
conn = sqlite3.connect(str(DB_PATH))

# ── Load tables ───────────────────────────────────────────────────────────────
nav = pd.read_sql_query("""
    SELECT f.scheme_name, d.calendar_date, n.nav
    FROM fact_nav n
    JOIN dim_fund f ON f.fund_key = n.fund_key
    JOIN dim_date d ON d.date_key = n.date_key
    ORDER BY d.calendar_date
""", conn, parse_dates=["calendar_date"])

perf = pd.read_sql_query("""
    SELECT f.scheme_name, f.scheme_category, f.fund_house, p.*
    FROM fact_performance p
    JOIN dim_fund f ON f.fund_key = p.fund_key
""", conn)

aum = pd.read_sql_query("""
    SELECT f.scheme_name, f.scheme_category, a.aum_value
    FROM fact_aum a
    JOIN dim_fund f ON f.fund_key = a.fund_key
""", conn)

tx = pd.read_sql_query("""
    SELECT f.scheme_name, d.calendar_date, t.investor_id, t.transaction_type,
           t.amount, t.units, t.nav as tx_nav, t.state
    FROM fact_transactions t
    JOIN dim_fund f ON f.fund_key = t.fund_key
    JOIN dim_date d ON d.date_key = t.transaction_date_key
    ORDER BY d.calendar_date
""", conn, parse_dates=["calendar_date"])

investors = pd.read_sql_query("SELECT * FROM dim_investor", conn)

nifty = pd.read_sql_query("""
    SELECT d.calendar_date, n.nifty_close
    FROM fact_nifty50 n
    JOIN dim_date d ON d.date_key = n.date_key
    ORDER BY d.calendar_date
""", conn, parse_dates=["calendar_date"])

conn.close()
print(f"  Loaded: {len(nav):,} NAV rows | {len(tx):,} transactions | {len(investors)} investors")

# ── 1. Performance Summary CSV ────────────────────────────────────────────────
perf_out = perf[['scheme_name', 'scheme_category', 'fund_house',
                  'return_1m', 'return_3m', 'return_1y', 'return_3y', 'return_5y',
                  'volatility', 'sharpe_ratio', 'anomaly_flag']].copy()
perf_out.to_csv(REPORTS / "performance_summary.csv", index=False)
print("[DONE] performance_summary.csv")

# ── 2. AUM Summary CSV ────────────────────────────────────────────────────────
aum.to_csv(REPORTS / "aum_summary.csv", index=False)
print("[DONE] aum_summary.csv")

# ── 3. Transaction Summary CSV ────────────────────────────────────────────────
tx_monthly = (
    tx.assign(month=tx['calendar_date'].dt.to_period('M').astype(str))
    .groupby(['month', 'transaction_type'])['amount']
    .sum()
    .reset_index()
)
tx_monthly.to_csv(REPORTS / "monthly_transactions.csv", index=False)
print("[DONE] monthly_transactions.csv")

# ── 4. VaR / CVaR CSV ────────────────────────────────────────────────────────
nav_pivot = nav.pivot(index="calendar_date", columns="scheme_name", values="nav").sort_index()
returns = nav_pivot.pct_change().dropna(how="all")

var_rows = []
for col in returns.columns:
    ret = returns[col].dropna()
    if len(ret) < 30:
        continue
    var95  = np.percentile(ret, 5)
    cvar95 = ret[ret <= var95].mean()
    var_rows.append({
        "Scheme": col.split(" - ")[0],
        "Full Name": col,
        "95% VaR Daily": round(var95 * 100, 4),
        "95% CVaR Daily": round(cvar95 * 100, 4),
        "VaR Annualized": round(var95 * np.sqrt(252) * 100, 2),
    })
pd.DataFrame(var_rows).to_csv(REPORTS / "var_cvar_report.csv", index=False)
print("[DONE] var_cvar_report.csv")

# ── 5. Rolling Sharpe Chart (PNG) ─────────────────────────────────────────────
RF_daily = 0.065 / 252
rolling_sharpe = pd.DataFrame(index=returns.index)
for col in returns.columns:
    mean90 = returns[col].rolling(90).mean()
    std90  = returns[col].rolling(90).std()
    rolling_sharpe[col] = ((mean90 - RF_daily) / std90.replace(0, np.nan)) * np.sqrt(252)

rolling_sharpe = rolling_sharpe.dropna(how="all")

fig, ax = plt.subplots(figsize=(13, 5))
for col in rolling_sharpe.columns:
    ax.plot(rolling_sharpe.index, rolling_sharpe[col],
            label=col.split(" - ")[0], linewidth=1.5)
ax.axhline(0, color="#94a3b8", linestyle="--", linewidth=1)
ax.set_title("Rolling 90-Day Sharpe Ratio (Risk-Free Rate: 6.5%)", fontsize=13, fontweight="bold")
ax.set_xlabel("Date")
ax.set_ylabel("Sharpe Ratio")
ax.legend(fontsize=8, loc="upper left")
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(REPORTS / "rolling_sharpe_chart.png", dpi=150)
plt.close(fig)
print("[DONE] rolling_sharpe_chart.png")

# ── 6. Monte Carlo Simulation Chart (first fund in DB) ───────────────────────
mc_col = list(returns.columns)[0]
fund_ret   = returns[mc_col].dropna()
log_ret    = np.log(1 + fund_ret)
mu_        = log_ret.mean()
var_logr   = log_ret.var()
drift      = mu_ - (0.5 * var_logr)
std_dev    = log_ret.std()

n_days = 5 * 252
S0     = nav_pivot[mc_col].dropna().iloc[-1]
n_sims = 1000

np.random.seed(42)
shocks = np.random.normal(0, 1, (n_days, n_sims))
daily_returns = np.exp(drift + std_dev * shocks)
paths    = np.zeros_like(daily_returns)
paths[0] = S0 * daily_returns[0]
for t in range(1, n_days):
    paths[t] = paths[t-1] * daily_returns[t]

p10 = np.percentile(paths, 10, axis=1)
p50 = np.percentile(paths, 50, axis=1)
p90 = np.percentile(paths, 90, axis=1)
time_idx = pd.date_range(start=nav_pivot.index[-1], periods=n_days, freq="B")

fig, ax = plt.subplots(figsize=(13, 5))
for i in range(min(50, n_sims)):
    ax.plot(time_idx, paths[:, i], alpha=0.05, color="#3b82f6")
ax.fill_between(time_idx, p10, p90, alpha=0.15, color="#3b82f6", label="80% CI")
ax.plot(time_idx, p50, color="#0f172a", linewidth=2.5, label="Median")
ax.plot(time_idx, p10, color="#ef4444", linewidth=1.5, linestyle="--", label="10th %ile")
ax.plot(time_idx, p90, color="#10b981", linewidth=1.5, linestyle="--", label="90th %ile")
ax.set_title(f"Monte Carlo 5-Year Projection — {mc_col.split(' - ')[0]} ({n_sims} simulations)",
             fontsize=12, fontweight="bold")
ax.set_xlabel("Date")
ax.set_ylabel("Projected NAV (₹)")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"₹{x:,.0f}"))
fig.tight_layout()
fig.savefig(REPORTS / "monte_carlo_simulation.png", dpi=150)
plt.close(fig)
print("[DONE] monte_carlo_simulation.png")

# ── 7. Efficient Frontier Chart ───────────────────────────────────────────────
ann_returns = returns.mean() * 252
cov_matrix  = returns.cov() * 252
n_funds     = len(returns.columns)
n_portfolios = 5000
res = np.zeros((3, n_portfolios))

np.random.seed(42)
for i in range(n_portfolios):
    w = np.random.random(n_funds)
    w /= w.sum()
    pr = np.sum(w * ann_returns)
    ps = np.sqrt(np.dot(w.T, np.dot(cov_matrix, w)))
    res[0, i] = pr
    res[1, i] = ps
    res[2, i] = (pr - 0.065) / ps if ps > 0 else 0

max_s = np.argmax(res[2])
min_v = np.argmin(res[1])

fig, ax = plt.subplots(figsize=(10, 6))
sc = ax.scatter(res[1] * 100, res[0] * 100, c=res[2], cmap="viridis", alpha=0.5, s=6)
ax.scatter(res[1, max_s] * 100, res[0, max_s] * 100,
           marker="*", color="#ef4444", s=300, zorder=5, label="Max Sharpe (MSR)")
ax.scatter(res[1, min_v] * 100, res[0, min_v] * 100,
           marker="*", color="#3b82f6", s=300, zorder=5, label="Min Volatility (MVP)")
plt.colorbar(sc, ax=ax, label="Sharpe Ratio")
ax.set_title("Markowitz Efficient Frontier (5,000 Random Portfolios)", fontsize=12, fontweight="bold")
ax.set_xlabel("Portfolio Volatility (%)")
ax.set_ylabel("Expected Annual Return (%)")
ax.legend(fontsize=9)
ax.grid(True, alpha=0.3)
fig.tight_layout()
fig.savefig(REPORTS / "efficient_frontier.png", dpi=150)
plt.close(fig)
print("[DONE] efficient_frontier.png")

# ── 8. NAV History Chart ──────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(13, 5))
for col in nav_pivot.columns:
    ax.plot(nav_pivot.index, nav_pivot[col],
            label=col.split(" - ")[0], linewidth=1.5)
ax.set_title("Historical NAV — All Schemes", fontsize=13, fontweight="bold")
ax.set_xlabel("Date")
ax.set_ylabel("NAV (₹)")
ax.legend(fontsize=8, loc="upper left")
ax.grid(True, alpha=0.3)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"₹{x:,.0f}"))
fig.tight_layout()
fig.savefig(REPORTS / "nav_history_all_funds.png", dpi=150)
plt.close(fig)
print("[DONE] nav_history_all_funds.png")

# ── 9. SIP Gap Analysis CSV ───────────────────────────────────────────────────
sip_txns = tx[tx['transaction_type'] == 'SIP'].copy()
sip_counts = sip_txns.groupby('investor_id').size()
eligible = sip_counts[sip_counts >= 6].index

gap_rows = []
for inv in eligible:
    inv_sip = sip_txns[sip_txns['investor_id'] == inv].sort_values('calendar_date')
    gaps = inv_sip['calendar_date'].diff().dt.days.dropna()
    if len(gaps) == 0:
        continue
    avg_gap = gaps.mean()
    gap_rows.append({
        "investor_id": inv,
        "sip_count": len(inv_sip),
        "avg_gap_days": round(avg_gap, 1),
        "status": "At-Risk (Gap > 35d)" if avg_gap > 35 else "Continuous"
    })

sip_gap_df = pd.DataFrame(gap_rows)
sip_gap_df.to_csv(REPORTS / "sip_gap_analysis.csv", index=False)
print(f"[DONE] sip_gap_analysis.csv ({len(sip_gap_df)} investors)")

# ── 10. Investor Demographics CSV ─────────────────────────────────────────────
investors.to_csv(REPORTS / "investor_demographics.csv", index=False)
print("[DONE] investor_demographics.csv")

# ── 11. Nifty50 vs Fund Returns Chart ────────────────────────────────────────
if not nifty.empty:
    nifty = nifty.set_index("calendar_date").sort_index()
    # Normalize to 100
    nifty_norm = (nifty["nifty_close"] / nifty["nifty_close"].iloc[0]) * 100

    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(nifty_norm.index, nifty_norm.values, label="NIFTY 50",
            color="#f59e0b", linewidth=2, linestyle="--")
    for col in nav_pivot.columns:
        s = nav_pivot[col].dropna()
        if len(s) < 10:
            continue
        s_norm = (s / s.iloc[0]) * 100
        ax.plot(s_norm.index, s_norm.values, label=col.split(" - ")[0], linewidth=1.5)
    ax.set_title("Fund NAV vs NIFTY 50 (Normalized to 100)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Date")
    ax.set_ylabel("Normalized Value")
    ax.legend(fontsize=8, loc="upper left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(REPORTS / "fund_vs_nifty.png", dpi=150)
    plt.close(fig)
    print("[DONE] fund_vs_nifty.png")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
report_files = sorted(REPORTS.iterdir())
print(f"{'='*60}")
print(f"  Reports directory: {REPORTS}")
print(f"  Total files: {len(report_files)}")
for f in report_files:
    size = f.stat().st_size
    print(f"  {f.name:<45} {size:>8,} bytes")
print(f"{'='*60}")
print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] All reports updated successfully!")
