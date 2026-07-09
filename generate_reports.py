"""
generate_reports.py — Master Report Generator
===============================================
Regenerates ALL CSV reports and chart PNGs from the live SQLite DB.
Includes the 4 dashboard page screenshots used in Tableau / presentations.

Run after any ETL or metric recomputation:
    python generate_reports.py
"""

import sqlite3
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import matplotlib.patches as mpatches
from pathlib import Path
from datetime import datetime
from scipy import stats

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE    = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "db" / "bluestock_mf.db"
REPORTS = BASE / "reports"
REPORTS.mkdir(exist_ok=True)

RF_DAILY = 0.065 / 252
N_DAYS   = 252

# ── Colour palette ─────────────────────────────────────────────────────────────
C_BLUE   = "#4154f1"
C_DARK   = "#012970"
C_ORANGE = "#F05537"
C_GREEN  = "#059652"
C_PINK   = "#f3268c"
C_GREY   = "#6c757d"
PALETTE  = [C_BLUE, C_GREEN, C_ORANGE, C_PINK, C_DARK, C_GREY]

print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Connecting to DB: {DB_PATH}")
conn = sqlite3.connect(str(DB_PATH))

# ── Load tables ────────────────────────────────────────────────────────────────
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
           t.amount, t.state
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

nav_pivot = nav.pivot(index="calendar_date", columns="scheme_name", values="nav").sort_index()
returns   = nav_pivot.pct_change().dropna(how="all")
scheme_names = list(nav_pivot.columns)
short_names  = [n.split(" - ")[0] for n in scheme_names]

print(f"  Loaded: {len(nav):,} NAV rows | {len(tx):,} transactions | {len(investors)} investors")


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def cagr(nav_s, n_years):
    n_td = int(n_years * N_DAYS)
    if len(nav_s) < n_td + 1:
        return np.nan
    return ((nav_s.iloc[-1] / nav_s.iloc[-(n_td + 1)]) ** (1 / n_years) - 1) * 100


def sharpe_ratio(ret):
    exc = ret - RF_DAILY
    sd  = exc.std()
    return float((exc.mean() / sd) * np.sqrt(N_DAYS)) if sd > 0 else np.nan


def max_drawdown(nav_s):
    roll_max  = nav_s.cummax()
    drawdowns = (nav_s / roll_max) - 1
    return float(drawdowns.min()) * 100


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — CSV REPORTS
# ══════════════════════════════════════════════════════════════════════════════

# 1. Performance summary
perf[['scheme_name','scheme_category','fund_house',
      'return_1m','return_3m','return_1y','return_3y','return_5y',
      'volatility','sharpe_ratio','anomaly_flag']].to_csv(
    REPORTS / "performance_summary.csv", index=False)
print("[DONE] performance_summary.csv")

# 2. AUM summary
aum.to_csv(REPORTS / "aum_summary.csv", index=False)
print("[DONE] aum_summary.csv")

# 3. Monthly transactions
tx_monthly = (tx.assign(month=tx['calendar_date'].dt.to_period('M').astype(str))
               .groupby(['month','transaction_type'])['amount'].sum().reset_index())
tx_monthly.to_csv(REPORTS / "monthly_transactions.csv", index=False)
print("[DONE] monthly_transactions.csv")

# 4. VaR / CVaR
var_rows = []
for col in scheme_names:
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
        "VaR Annualized": round(var95 * np.sqrt(N_DAYS) * 100, 2),
    })
pd.DataFrame(var_rows).to_csv(REPORTS / "var_cvar_report.csv", index=False)
print("[DONE] var_cvar_report.csv")

# 5. SIP gap analysis
sip_txns   = tx[tx['transaction_type'] == 'SIP'].copy()
sip_counts = sip_txns.groupby('investor_id').size()
eligible   = sip_counts[sip_counts >= 6].index
gap_rows   = []
for inv in eligible:
    inv_sip = sip_txns[sip_txns['investor_id'] == inv].sort_values('calendar_date')
    gaps    = inv_sip['calendar_date'].diff().dt.days.dropna()
    if len(gaps) == 0:
        continue
    avg_gap = gaps.mean()
    gap_rows.append({
        "investor_id": inv,
        "sip_count":   len(inv_sip),
        "avg_gap_days": round(avg_gap, 1),
        "status": "At-Risk (Gap > 35d)" if avg_gap > 35 else "Continuous",
    })
pd.DataFrame(gap_rows).to_csv(REPORTS / "sip_gap_analysis.csv", index=False)
print(f"[DONE] sip_gap_analysis.csv ({len(gap_rows)} investors)")

# 6. Investor demographics
investors.to_csv(REPORTS / "investor_demographics.csv", index=False)
print("[DONE] investor_demographics.csv")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — CHART PNGs (analytics)
# ══════════════════════════════════════════════════════════════════════════════

# 7. Rolling Sharpe
fig, ax = plt.subplots(figsize=(13, 5))
for i, col in enumerate(scheme_names):
    mean90 = returns[col].rolling(90).mean()
    std90  = returns[col].rolling(90).std()
    rs     = ((mean90 - RF_DAILY) / std90.replace(0, np.nan)) * np.sqrt(N_DAYS)
    ax.plot(rs.index, rs.values, label=col.split(" - ")[0],
            color=PALETTE[i % len(PALETTE)], linewidth=1.5)
ax.axhline(0, color="#94a3b8", linestyle="--", linewidth=1)
ax.set_title("Rolling 90-Day Sharpe Ratio (Rf = 6.5%)", fontsize=13, fontweight="bold")
ax.set_xlabel("Date"); ax.set_ylabel("Sharpe Ratio")
ax.legend(fontsize=8, loc="upper left"); ax.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(REPORTS / "rolling_sharpe_chart.png", dpi=150); plt.close(fig)
print("[DONE] rolling_sharpe_chart.png")

# 8. Monte Carlo (first fund)
mc_col  = scheme_names[0]
fr      = returns[mc_col].dropna()
lr      = np.log(1 + fr)
mu, var_logr = lr.mean(), lr.var()
drift   = mu - 0.5 * var_logr
sd      = lr.std()
n_days  = 5 * N_DAYS
S0      = nav_pivot[mc_col].dropna().iloc[-1]
n_sims  = 1000
np.random.seed(42)
shocks  = np.random.normal(0, 1, (n_days, n_sims))
dr      = np.exp(drift + sd * shocks)
paths   = np.zeros_like(dr); paths[0] = S0 * dr[0]
for t in range(1, n_days):
    paths[t] = paths[t-1] * dr[t]
time_idx = pd.date_range(start=nav_pivot.index[-1], periods=n_days, freq="B")
p10, p50, p90 = [np.percentile(paths, q, axis=1) for q in [10, 50, 90]]

fig, ax = plt.subplots(figsize=(13, 5))
for i in range(min(50, n_sims)):
    ax.plot(time_idx, paths[:, i], alpha=0.05, color=C_BLUE)
ax.fill_between(time_idx, p10, p90, alpha=0.15, color=C_BLUE, label="80% CI")
ax.plot(time_idx, p50, color=C_DARK, linewidth=2.5, label="Median")
ax.plot(time_idx, p10, color=C_ORANGE, linewidth=1.5, linestyle="--", label="10th %ile")
ax.plot(time_idx, p90, color=C_GREEN, linewidth=1.5, linestyle="--", label="90th %ile")
ax.set_title(f"Monte Carlo 5-Year Projection — {mc_col.split(' - ')[0]} ({n_sims} simulations)",
             fontsize=12, fontweight="bold")
ax.set_xlabel("Date"); ax.set_ylabel("Projected NAV (₹)")
ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"₹{x:,.0f}"))
fig.tight_layout(); fig.savefig(REPORTS / "monte_carlo_simulation.png", dpi=150); plt.close(fig)
print("[DONE] monte_carlo_simulation.png")

# 9. Efficient Frontier
ann_ret  = returns.mean() * N_DAYS
cov_mat  = returns.cov() * N_DAYS
n_funds  = len(scheme_names)
n_ports  = 5000
res      = np.zeros((3, n_ports))
np.random.seed(42)
for i in range(n_ports):
    w = np.random.random(n_funds); w /= w.sum()
    pr = np.sum(w * ann_ret)
    ps = np.sqrt(np.dot(w.T, np.dot(cov_mat, w)))
    res[0, i] = pr; res[1, i] = ps
    res[2, i] = (pr - 0.065) / ps if ps > 0 else 0
max_s, min_v = np.argmax(res[2]), np.argmin(res[1])

fig, ax = plt.subplots(figsize=(10, 6))
sc = ax.scatter(res[1]*100, res[0]*100, c=res[2], cmap="viridis", alpha=0.5, s=6)
ax.scatter(res[1, max_s]*100, res[0, max_s]*100,
           marker="*", color=C_ORANGE, s=300, zorder=5, label="Max Sharpe (MSR)")
ax.scatter(res[1, min_v]*100, res[0, min_v]*100,
           marker="*", color=C_BLUE, s=300, zorder=5, label="Min Volatility (MVP)")
plt.colorbar(sc, ax=ax, label="Sharpe Ratio")
ax.set_title("Markowitz Efficient Frontier (5,000 Portfolios)", fontsize=12, fontweight="bold")
ax.set_xlabel("Volatility (%)"); ax.set_ylabel("Expected Return (%)")
ax.legend(fontsize=9); ax.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(REPORTS / "efficient_frontier.png", dpi=150); plt.close(fig)
print("[DONE] efficient_frontier.png")

# 10. NAV history all funds
fig, ax = plt.subplots(figsize=(13, 5))
for i, col in enumerate(scheme_names):
    ax.plot(nav_pivot.index, nav_pivot[col], label=col.split(" - ")[0],
            color=PALETTE[i % len(PALETTE)], linewidth=1.5)
ax.set_title("Historical NAV — All Schemes", fontsize=13, fontweight="bold")
ax.set_xlabel("Date"); ax.set_ylabel("NAV (₹)")
ax.legend(fontsize=8, loc="upper left"); ax.grid(True, alpha=0.3)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"₹{x:,.0f}"))
fig.tight_layout(); fig.savefig(REPORTS / "nav_history_all_funds.png", dpi=150); plt.close(fig)
print("[DONE] nav_history_all_funds.png")

# 11. Fund vs Nifty
nifty_s = nifty.set_index("calendar_date")["nifty_close"].sort_index()
fig, ax = plt.subplots(figsize=(13, 5))
nifty_norm = (nifty_s / nifty_s.iloc[0]) * 100
ax.plot(nifty_norm.index, nifty_norm, label="NIFTY 50",
        color=C_ORANGE, linewidth=2, linestyle="--")
for i, col in enumerate(scheme_names):
    s = nav_pivot[col].dropna()
    ax.plot(s.index, (s / s.iloc[0]) * 100, label=col.split(" - ")[0],
            color=PALETTE[i % len(PALETTE)], linewidth=1.5)
ax.set_title("Fund NAV vs NIFTY 50 (Normalised to 100)", fontsize=12, fontweight="bold")
ax.set_xlabel("Date"); ax.set_ylabel("Normalised Value")
ax.legend(fontsize=8, loc="upper left"); ax.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(REPORTS / "fund_vs_nifty.png", dpi=150); plt.close(fig)
print("[DONE] fund_vs_nifty.png")


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — 4 DASHBOARD PAGE PNGs
# ══════════════════════════════════════════════════════════════════════════════

plt.rcParams.update({
    "font.family":  "DejaVu Sans",
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "axes.titlesize":     11,
    "axes.labelsize":     9,
    "xtick.labelsize":    8,
    "ytick.labelsize":    8,
})

PAGE_W, PAGE_H = 16, 9   # inches
PAGE_DPI       = 150

def page_header(fig, title: str, subtitle: str = "") -> None:
    """Draw a dark top banner on the figure."""
    ax_hdr = fig.add_axes([0, 0.92, 1, 0.08])
    ax_hdr.set_facecolor(C_DARK)
    ax_hdr.axis("off")
    ax_hdr.text(0.02, 0.65, title, color="white", fontsize=14,
                fontweight="bold", va="center", transform=ax_hdr.transAxes)
    ax_hdr.text(0.02, 0.2, subtitle, color="#a5c8ff", fontsize=8,
                va="center", transform=ax_hdr.transAxes)
    ax_hdr.text(0.98, 0.5, "Bluestock Fintech | Mutual Fund Analytics",
                color="#a5c8ff", fontsize=7, ha="right", va="center",
                transform=ax_hdr.transAxes)


def kpi_card(ax, value: str, label: str, colour: str = C_BLUE) -> None:
    ax.set_facecolor("#f8fafc")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    rect = FancyBboxPatch((0.05, 0.05), 0.9, 0.9,
                          boxstyle="round,pad=0.02",
                          facecolor="white", edgecolor=colour, linewidth=2)
    ax.add_patch(rect)
    ax.text(0.5, 0.62, value, ha="center", va="center", fontsize=16,
            fontweight="bold", color=C_DARK)
    ax.text(0.5, 0.28, label, ha="center", va="center", fontsize=8,
            color=C_GREY)
    ax.plot([0.05, 0.95], [0.07, 0.07], color=colour, linewidth=3,
            transform=ax.transAxes, clip_on=False,
            solid_capstyle="round")


# ── Page 1: Industry & AUM Overview ──────────────────────────────────────────
fig = plt.figure(figsize=(PAGE_W, PAGE_H), facecolor="#f0f4ff")
page_header(fig, "[1] Industry & AUM Overview",
            "Total AUM, SIP inflows, fund allocation, and monthly transaction trends")

gs = gridspec.GridSpec(3, 4, figure=fig,
                       top=0.90, bottom=0.06, left=0.05, right=0.97,
                       hspace=0.45, wspace=0.35)

total_aum  = aum["aum_value"].sum()
n_folios   = len(investors)
n_txns     = len(tx)
n_schemes  = len(nav_pivot.columns)

# KPI cards
for j, (val, lbl, col) in enumerate([
    (f"₹{total_aum:,.1f} Cr", "Total Tracked AUM",   C_BLUE),
    (f"{n_folios:,}",          "Tracked Folios",        C_GREEN),
    (f"{n_txns:,}",            "Total Transactions",    C_ORANGE),
    (f"{n_schemes}",           "Tracked Schemes",       C_PINK),
]):
    ax = fig.add_subplot(gs[0, j])
    kpi_card(ax, val, lbl, col)

# AUM by scheme
ax1 = fig.add_subplot(gs[1:, :2])
aum_s = aum.copy()
aum_s["short"] = aum_s["scheme_name"].apply(lambda x: x.split(" - ")[0])
bars = ax1.barh(aum_s["short"], aum_s["aum_value"],
                color=PALETTE[:len(aum_s)])
ax1.set_xlabel("AUM (₹ Cr)"); ax1.set_title("AUM by Scheme")
ax1.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"₹{x:,.0f}"))
for bar in bars:
    ax1.text(bar.get_width() * 1.01, bar.get_y() + bar.get_height() / 2,
             f"₹{bar.get_width():,.1f}", va="center", fontsize=7)

# Monthly transactions
ax2 = fig.add_subplot(gs[1:, 2:])
tx_m = (tx.assign(month=tx["calendar_date"].dt.to_period("M").astype(str))
          .groupby(["month", "transaction_type"])["amount"].sum().unstack(fill_value=0))
colors_tx = [C_BLUE, C_ORANGE]
for i, col in enumerate(tx_m.columns):
    ax2.plot(range(len(tx_m)), tx_m[col] / 1e6,
             label=col, color=colors_tx[i % 2], linewidth=1.5)
ax2.set_xlabel("Month"); ax2.set_ylabel("Amount (₹ Mn)")
ax2.set_title("Monthly Transaction Amounts")
step = max(1, len(tx_m) // 6)
ax2.set_xticks(range(0, len(tx_m), step))
ax2.set_xticklabels(tx_m.index[::step], rotation=35, ha="right", fontsize=7)
ax2.legend(fontsize=8); ax2.grid(True, alpha=0.3)

fig.savefig(REPORTS / "Page1_Industry_Overview.png", dpi=PAGE_DPI, bbox_inches="tight")
plt.close(fig)
print("[DONE] Page1_Industry_Overview.png")


# ── Page 2: Fund Performance Scorecard ───────────────────────────────────────
fig = plt.figure(figsize=(PAGE_W, PAGE_H), facecolor="#f0f4ff")
page_header(fig, "[2] Fund Performance Scorecard",
            "Returns, risk metrics, Sharpe ratio, and historical NAV trend")

gs = gridspec.GridSpec(2, 2, figure=fig,
                       top=0.90, bottom=0.06, left=0.06, right=0.97,
                       hspace=0.40, wspace=0.30)

# Risk-Return scatter
ax1 = fig.add_subplot(gs[0, 0])
if not perf.empty and "return_1y" in perf.columns and "volatility" in perf.columns:
    colors_s = [PALETTE[i % len(PALETTE)] for i in range(len(perf))]
    for i, row in perf.iterrows():
        ax1.scatter(row["volatility"], row["return_1y"], s=80,
                    color=PALETTE[i % len(PALETTE)], zorder=3)
        lbl = row["scheme_name"].split(" - ")[0][:20]
        ax1.annotate(lbl, (row["volatility"], row["return_1y"]),
                     xytext=(4, 4), textcoords="offset points", fontsize=6)
ax1.set_xlabel("Volatility (%)"); ax1.set_ylabel("1Y Return (%)")
ax1.set_title("Risk vs Return (1Y)"); ax1.grid(True, alpha=0.3)

# Sharpe bar chart
ax2 = fig.add_subplot(gs[0, 1])
if not perf.empty and "sharpe_ratio" in perf.columns:
    sh_data = perf[["scheme_name", "sharpe_ratio"]].dropna().sort_values("sharpe_ratio")
    sh_data["short"] = sh_data["scheme_name"].apply(lambda x: x.split(" - ")[0])
    colors_sh = [C_GREEN if v >= 0 else C_ORANGE for v in sh_data["sharpe_ratio"]]
    ax2.barh(sh_data["short"], sh_data["sharpe_ratio"], color=colors_sh)
    ax2.axvline(0, color=C_DARK, linewidth=1)
    ax2.set_xlabel("Sharpe Ratio"); ax2.set_title("Sharpe Ratio by Fund")

# CAGR comparison
ax3 = fig.add_subplot(gs[1, 0])
if not perf.empty:
    perf_s = perf[["scheme_name", "return_1y", "return_3y", "return_5y"]].dropna().copy()
    perf_s["short"] = perf_s["scheme_name"].apply(lambda x: x.split(" - ")[0][:18])
    x    = np.arange(len(perf_s))
    w    = 0.25
    ax3.bar(x - w, perf_s["return_1y"], w, label="1Y", color=C_BLUE)
    ax3.bar(x,     perf_s["return_3y"], w, label="3Y", color=C_GREEN)
    ax3.bar(x + w, perf_s["return_5y"], w, label="5Y", color=C_ORANGE)
    ax3.set_xticks(x)
    ax3.set_xticklabels(perf_s["short"], rotation=35, ha="right", fontsize=7)
    ax3.set_ylabel("Return (%)"); ax3.set_title("CAGR Comparison (1Y / 3Y / 5Y)")
    ax3.legend(fontsize=8); ax3.grid(True, alpha=0.3, axis="y")

# NAV trend
ax4 = fig.add_subplot(gs[1, 1])
for i, col in enumerate(scheme_names[:4]):
    s = nav_pivot[col].dropna()
    ax4.plot(s.index, (s / s.iloc[0]) * 100,
             label=col.split(" - ")[0][:18], color=PALETTE[i], linewidth=1.5)
nifty_s2 = nifty.set_index("calendar_date")["nifty_close"].sort_index()
ax4.plot(nifty_s2.index, (nifty_s2 / nifty_s2.iloc[0]) * 100,
         label="NIFTY 50", color=C_DARK, linewidth=2, linestyle="--")
ax4.set_xlabel("Date"); ax4.set_ylabel("Normalised (Base 100)")
ax4.set_title("NAV vs NIFTY 50 (Normalised)"); ax4.legend(fontsize=7); ax4.grid(True, alpha=0.3)

fig.savefig(REPORTS / "Page2_Fund_Performance.png", dpi=PAGE_DPI, bbox_inches="tight")
plt.close(fig)
print("[DONE] Page2_Fund_Performance.png")


# ── Page 3: Investor Analytics ────────────────────────────────────────────────
fig = plt.figure(figsize=(PAGE_W, PAGE_H), facecolor="#f0f4ff")
page_header(fig, "[3] Investor Analytics",
            "Demographic distribution, state inflows, SIP/Lumpsum split, age group analysis")

gs = gridspec.GridSpec(2, 3, figure=fig,
                       top=0.90, bottom=0.06, left=0.06, right=0.97,
                       hspace=0.45, wspace=0.35)

# Top states
ax1 = fig.add_subplot(gs[0, :2])
state_inf = (tx.groupby("state")["amount"].sum()
               .sort_values(ascending=False).head(10).reset_index())
ax1.barh(state_inf["state"][::-1], state_inf["amount"][::-1] / 1e6,
         color=C_BLUE)
ax1.set_xlabel("Total Inflows (₹ Mn)"); ax1.set_title("Top 10 States by Transaction Inflows")
ax1.grid(True, alpha=0.3, axis="x")

# SIP vs Lumpsum donut
ax2 = fig.add_subplot(gs[0, 2])
type_split = tx.groupby("transaction_type")["amount"].sum()
wedges, texts, autotexts = ax2.pie(
    type_split, labels=type_split.index, autopct="%1.1f%%",
    colors=[C_BLUE, C_ORANGE], startangle=90,
    wedgeprops=dict(width=0.55))
ax2.set_title("SIP vs Lumpsum Split")

# Age group vs Avg SIP
ax3 = fig.add_subplot(gs[1, :2])
if "age_group" in investors.columns and "sip_amount" in investors.columns:
    age_sip = (investors.groupby("age_group")["sip_amount"].mean()
                         .sort_index().reset_index())
    bars3 = ax3.bar(age_sip["age_group"], age_sip["sip_amount"],
                    color=PALETTE[:len(age_sip)])
    for bar in bars3:
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 30,
                 f"₹{bar.get_height():,.0f}", ha="center", fontsize=7)
    ax3.set_xlabel("Age Group"); ax3.set_ylabel("Avg SIP Amount (₹)")
    ax3.set_title("Average SIP Amount by Age Group"); ax3.grid(True, alpha=0.3, axis="y")

# Monthly registrations
ax4 = fig.add_subplot(gs[1, 2])
if "registration_date" in investors.columns:
    reg = investors.copy()
    reg["reg_date"] = pd.to_datetime(reg["registration_date"], errors="coerce")
    reg_m = (reg.groupby(reg["reg_date"].dt.to_period("M"))["investor_id"]
               .count().reset_index())
    reg_m["reg_date"] = reg_m["reg_date"].astype(str)
    ax4.plot(range(len(reg_m)), reg_m["investor_id"],
             color=C_GREEN, linewidth=2, marker="o", markersize=4)
    step4 = max(1, len(reg_m) // 5)
    ax4.set_xticks(range(0, len(reg_m), step4))
    ax4.set_xticklabels(reg_m["reg_date"].iloc[::step4], rotation=35, ha="right", fontsize=7)
    ax4.set_ylabel("New Registrations"); ax4.set_title("Monthly Investor Registrations")
    ax4.grid(True, alpha=0.3)

fig.savefig(REPORTS / "Page3_Investor_Analytics.png", dpi=PAGE_DPI, bbox_inches="tight")
plt.close(fig)
print("[DONE] Page3_Investor_Analytics.png")


# ── Page 4: SIP & Market Trends ───────────────────────────────────────────────
fig = plt.figure(figsize=(PAGE_W, PAGE_H), facecolor="#f0f4ff")
page_header(fig, "[4] SIP & Market Trends",
            "SIP inflow trend vs NIFTY 50, category heatmap, and at-risk investor analysis")

gs = gridspec.GridSpec(2, 2, figure=fig,
                       top=0.90, bottom=0.06, left=0.06, right=0.97,
                       hspace=0.40, wspace=0.30)

# Dual axis: SIP bar + Nifty line
ax1 = fig.add_subplot(gs[0, :])
sip_m = (tx[tx["transaction_type"] == "SIP"]
           .assign(month=tx["calendar_date"].dt.to_period("M").astype(str))
           .groupby("month")["amount"].sum())
ax1b = ax1.twinx()
ax1.bar(range(len(sip_m)), sip_m / 1e6, color=C_BLUE, alpha=0.7, label="SIP Inflow")
# Nifty monthly close
nifty_m = (nifty.set_index("calendar_date")["nifty_close"]
               .resample("M").last().reset_index())
nifty_m["month"] = nifty_m["calendar_date"].dt.to_period("M").astype(str)
nifty_common = nifty_m[nifty_m["month"].isin(sip_m.index)]
nifty_x = [list(sip_m.index).index(m) for m in nifty_common["month"] if m in list(sip_m.index)]
ax1b.plot(nifty_x, nifty_common["nifty_close"].values,
          color=C_ORANGE, linewidth=2, label="NIFTY 50")
ax1.set_ylabel("SIP Inflow (₹ Mn)", color=C_BLUE)
ax1b.set_ylabel("NIFTY 50 Close", color=C_ORANGE)
ax1.set_title("SIP Inflow (Bar) vs NIFTY 50 (Line)")
step5 = max(1, len(sip_m) // 8)
ax1.set_xticks(range(0, len(sip_m), step5))
ax1.set_xticklabels(list(sip_m.index)[::step5], rotation=35, ha="right", fontsize=7)
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax1b.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=8)
ax1.grid(True, alpha=0.3, axis="y")

# SIP gap KPIs
gap_csv = REPORTS / "sip_gap_analysis.csv"
if gap_csv.exists():
    gap_df = pd.read_csv(gap_csv)
    at_risk = len(gap_df[gap_df["status"] == "At-Risk (Gap > 35d)"])
    total_a = len(gap_df)
    pct_r   = at_risk / total_a * 100 if total_a > 0 else 0

    ax2 = fig.add_subplot(gs[1, 0])
    ax2.axis("off")
    ax2.text(0.5, 0.80, "Investors Analysed",    ha="center", fontsize=10, color=C_GREY)
    ax2.text(0.5, 0.60, str(total_a),             ha="center", fontsize=28, fontweight="bold", color=C_DARK)
    ax2.text(0.5, 0.40, "At-Risk Investors",      ha="center", fontsize=10, color=C_GREY)
    ax2.text(0.5, 0.20, str(at_risk),             ha="center", fontsize=28, fontweight="bold", color=C_ORANGE)
    ax2.text(0.5, 0.04, f"At-Risk Rate: {pct_r:.1f}%", ha="center", fontsize=11, color=C_PINK)
    ax2.set_title("SIP Continuity KPIs")

    ax3 = fig.add_subplot(gs[1, 1])
    bins = [0, 30, 60, 90, 120, 200]
    hist_data = gap_df["avg_gap_days"].dropna()
    n_vals, edges, patches = ax3.hist(hist_data, bins=bins, color=C_BLUE, edgecolor="white")
    ax3.axvline(35, color=C_ORANGE, linestyle="--", linewidth=2, label="At-Risk threshold (35d)")
    ax3.set_xlabel("Avg Gap Between SIPs (days)"); ax3.set_ylabel("Investor Count")
    ax3.set_title("SIP Gap Distribution"); ax3.legend(fontsize=8); ax3.grid(True, alpha=0.3, axis="y")

fig.savefig(REPORTS / "Page4_SIP_Market_Trends.png", dpi=PAGE_DPI, bbox_inches="tight")
plt.close(fig)
print("[DONE] Page4_SIP_Market_Trends.png")


# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
report_files = sorted(REPORTS.iterdir())
print(f"\n{'='*62}")
print(f"  Reports directory : {REPORTS}")
print(f"  Total files       : {len(report_files)}")
for f in report_files:
    size = f.stat().st_size
    print(f"  {f.name:<45} {size:>9,} bytes")
print(f"{'='*62}")
print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] All reports updated successfully!")
