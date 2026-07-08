import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ── Page Configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Mutual Fund Analytics | Bluestock Fintech",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Google Fonts (must be separate from style block) ────────────────────────
st.markdown(
    '<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&display=swap" rel="stylesheet">',
    unsafe_allow_html=True
)

# ── Premium CSS Styling ───────────────────────────────────────────────────────
st.markdown("""<style>
    /* ── Base ── */
    .stApp {
        background: linear-gradient(135deg, #f0f4ff 0%, #f8fafc 100%);
        color: #1e293b;
        font-family: 'Poppins', sans-serif !important;
    }
    html, body, [class*="css"] {
        font-family: 'Poppins', sans-serif !important;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
        border-right: 1px solid #334155;
    }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown h2 {
        color: #f1f5f9 !important;
    }
    section[data-testid="stSidebar"] label {
        color: #cbd5e1 !important;
    }

    /* ── KPI Cards ── */
    .kpi-card {
        background: #ffffff;
        padding: 22px 20px 18px 20px;
        border-radius: 16px;
        box-shadow: 0 4px 20px rgba(15, 23, 42, 0.07);
        border-bottom: 4px solid #38bdf8;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        min-height: 110px;
    }
    .kpi-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
    }
    .kpi-title {
        font-size: 11px;
        font-weight: 700;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 1.2px;
        margin-bottom: 10px;
    }
    .kpi-value {
        font-size: 30px;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.1;
    }
    .kpi-sub {
        font-size: 12px;
        color: #94a3b8;
        margin-top: 4px;
    }

    /* ── Page Header Banner ── */
    .page-banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
        color: #f1f5f9;
        padding: 28px 32px;
        border-radius: 16px;
        margin-bottom: 28px;
    }
    .page-banner h1 {
        color: #f1f5f9 !important;
        font-size: 26px !important;
        font-weight: 800 !important;
        margin: 0 !important;
    }
    .page-banner p {
        color: #94a3b8 !important;
        margin: 6px 0 0 0 !important;
        font-size: 14px !important;
    }

    /* ── Section Titles ── */
    .section-title {
        font-size: 16px;
        font-weight: 700;
        color: #1e293b;
        margin: 24px 0 12px 0;
        padding-bottom: 8px;
        border-bottom: 2px solid #e2e8f0;
    }

    /* ── Data Tables ── */
    div[data-testid="stDataFrame"] {
        border-radius: 12px !important;
        overflow: hidden !important;
        border: 1px solid #e2e8f0 !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        background: #f1f5f9;
        border-radius: 12px;
        padding: 4px;
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        font-weight: 600;
        color: #64748b;
    }
    .stTabs [aria-selected="true"] {
        background: #ffffff !important;
        color: #0f172a !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }

    /* ── Buttons ── */
    .stButton > button {
        background: linear-gradient(135deg, #3b82f6, #6366f1);
        color: white;
        border: none;
        border-radius: 10px;
        font-weight: 600;
        font-family: 'Poppins', sans-serif;
        padding: 10px 24px;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #2563eb, #4f46e5);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.4);
    }

    /* ── Alerts ── */
    .info-box {
        background: #eff6ff;
        border-left: 4px solid #3b82f6;
        padding: 12px 16px;
        border-radius: 8px;
        font-size: 13px;
        color: #1e40af;
        margin: 8px 0;
    }
    </style>
""", unsafe_allow_html=True)

# ── Database Connection ───────────────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "db" / "bluestock_mf.db"

@st.cache_resource
def get_connection():
    if not DB_PATH.exists():
        st.error(f"SQLite Database not found at: {DB_PATH}")
        return None
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)

conn = get_connection()

# ── Data Loaders ──────────────────────────────────────────────────────────────
@st.cache_data
def load_dim_funds():
    if conn is None: return pd.DataFrame()
    return pd.read_sql_query("SELECT * FROM dim_fund", conn)

@st.cache_data
def load_fact_performance():
    if conn is None: return pd.DataFrame()
    return pd.read_sql_query("""
        SELECT f.scheme_name, f.fund_house, f.scheme_category, p.*
        FROM fact_performance p
        JOIN dim_fund f ON f.fund_key = p.fund_key
    """, conn)

@st.cache_data
def load_fact_aum():
    if conn is None: return pd.DataFrame()
    return pd.read_sql_query("""
        SELECT f.scheme_name, f.scheme_category, a.*
        FROM fact_aum a
        JOIN dim_fund f ON f.fund_key = a.fund_key
    """, conn)

@st.cache_data
def load_fact_nav():
    if conn is None: return pd.DataFrame()
    return pd.read_sql_query("""
        SELECT f.scheme_name, d.calendar_date, n.nav
        FROM fact_nav n
        JOIN dim_fund f ON f.fund_key = n.fund_key
        JOIN dim_date d ON d.date_key = n.date_key
        ORDER BY d.calendar_date
    """, conn, parse_dates=["calendar_date"])

@st.cache_data
def load_fact_transactions():
    if conn is None: return pd.DataFrame()
    # Note: fact_transactions already contains state column; do NOT join dim_investor
    # here as t.* + i.state creates duplicate 'state' causing groupby crash
    return pd.read_sql_query("""
        SELECT f.scheme_name, d.calendar_date, t.*
        FROM fact_transactions t
        JOIN dim_fund f ON f.fund_key = t.fund_key
        JOIN dim_date d ON d.date_key = t.transaction_date_key
        ORDER BY d.calendar_date
    """, conn, parse_dates=["calendar_date"])

@st.cache_data
def load_dim_investors():
    if conn is None: return pd.DataFrame()
    return pd.read_sql_query("SELECT * FROM dim_investor", conn)

@st.cache_data
def load_nifty50():
    if conn is None: return pd.DataFrame()
    return pd.read_sql_query("""
        SELECT d.calendar_date, n.nifty_close
        FROM fact_nifty50 n
        JOIN dim_date d ON d.date_key = n.date_key
        ORDER BY d.calendar_date
    """, conn, parse_dates=["calendar_date"])

# ── Load all datasets ─────────────────────────────────────────────────────────
dim_funds    = load_dim_funds()
perf_data    = load_fact_performance()
aum_data     = load_fact_aum()
nav_data     = load_fact_nav()
tx_data      = load_fact_transactions()
investors    = load_dim_investors()
nifty        = load_nifty50()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.markdown("""
    <div style='text-align:center; padding: 16px 0 8px 0;'>
        <div style='font-size:28px;'>📊</div>
        <h2 style='color:#38bdf8; margin:6px 0 2px 0; font-size:18px; font-weight:800;'>Bluestock Fintech</h2>
        <p style='color:#64748b; font-size:12px; margin:0;'>Mutual Fund Analytics Platform</p>
    </div>
""", unsafe_allow_html=True)
st.sidebar.markdown("<hr style='border-color:#334155; margin: 12px 0;'>", unsafe_allow_html=True)

page = st.sidebar.radio(
    "Navigate",
    ["📊 Industry & AUM Overview",
     "📈 Fund Performance Scorecard",
     "👥 Investor Demographics",
     "⚠️ SIP Continuity & Gaps",
     "🔮 Advanced Analytics & Recommender"]
)

st.sidebar.markdown("<hr style='border-color:#334155; margin: 12px 0;'>", unsafe_allow_html=True)
st.sidebar.markdown("""
    <div style='padding: 8px 0; color: #475569; font-size: 11px;'>
        <b style='color:#94a3b8;'>Data Source:</b> mfapi.in + AMFI<br>
        <b style='color:#94a3b8;'>DB:</b> SQLite (6 schemes, ~20K NAV rows)<br>
        <b style='color:#94a3b8;'>Updated:</b> June 2026
    </div>
""", unsafe_allow_html=True)

# ── Helper: page banner ───────────────────────────────────────────────────────
def page_banner(title, subtitle):
    st.markdown(f"""
        <div class="page-banner">
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
    """, unsafe_allow_html=True)

def section_title(text):
    st.markdown(f"<div class='section-title'>{text}</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — INDUSTRY & AUM OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Industry & AUM Overview":
    page_banner("📊 Mutual Fund Industry & AUM Overview",
                "Real-time KPI summaries, AUM allocation, and monthly transaction trends")

    # ── Dynamic KPI Cards ─────────────────────────────────────────────────────
    total_aum     = aum_data['aum_value'].sum() if not aum_data.empty else 0
    total_folios  = len(investors) if not investors.empty else 0
    total_txns    = len(tx_data) if not tx_data.empty else 0
    total_schemes = len(dim_funds) if not dim_funds.empty else 0

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""
            <div class='kpi-card'>
                <div class='kpi-title'>Total Tracked AUM</div>
                <div class='kpi-value'>₹{total_aum:,.1f} Cr</div>
                <div class='kpi-sub'>Across {total_schemes} schemes</div>
            </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
            <div class='kpi-card' style='border-bottom:4px solid #10b981;'>
                <div class='kpi-title'>Tracked Folios</div>
                <div class='kpi-value'>{total_folios:,}</div>
                <div class='kpi-sub'>Unique investors</div>
            </div>
        """, unsafe_allow_html=True)
    with k3:
        st.markdown(f"""
            <div class='kpi-card' style='border-bottom:4px solid #f59e0b;'>
                <div class='kpi-title'>Total Transactions</div>
                <div class='kpi-value'>{total_txns:,}</div>
                <div class='kpi-sub'>SIP + Lumpsum</div>
            </div>
        """, unsafe_allow_html=True)
    with k4:
        st.markdown(f"""
            <div class='kpi-card' style='border-bottom:4px solid #ec4899;'>
                <div class='kpi-title'>Tracked Schemes</div>
                <div class='kpi-value'>{total_schemes}</div>
                <div class='kpi-sub'>Direct plan funds</div>
            </div>
        """, unsafe_allow_html=True)

    st.write("")

    # ── Charts Row 1 ──────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        section_title("AUM by Scheme (₹ Crore)")
        if not aum_data.empty:
            aum_clean = aum_data.copy()
            aum_clean['scheme_short'] = aum_clean['scheme_name'].apply(lambda x: x.split(" - ")[0])
            fig_aum = px.bar(
                aum_clean,
                x='scheme_short', y='aum_value',
                labels={'scheme_short': 'Scheme', 'aum_value': 'AUM (\u20b9 Cr)'},
                color='scheme_short',
                color_discrete_sequence=px.colors.qualitative.Plotly
            )
            fig_aum.update_layout(showlegend=False, template="plotly_white",
                                  xaxis_tickangle=-30, margin=dict(t=10, b=60))
            st.plotly_chart(fig_aum, use_container_width=True)
        else:
            st.info("No AUM data available.")

    with col2:
        section_title("AUM Distribution by Category")
        if not aum_data.empty:
            cat_aum = aum_data.groupby('scheme_category')['aum_value'].sum().reset_index()
            fig_pie = px.pie(
                cat_aum, values='aum_value', names='scheme_category',
                hole=0.42,
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            fig_pie.update_layout(template="plotly_white", margin=dict(t=10))
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No AUM data available.")

    # ── Monthly Transaction Trend ─────────────────────────────────────────────
    section_title("Monthly Transaction Amounts Over Time")
    if not tx_data.empty:
        tx_grouped = tx_data.copy()
        tx_grouped['month'] = tx_grouped['calendar_date'].dt.to_period('M').astype(str)
        tx_monthly = tx_grouped.groupby(['month', 'transaction_type'])['amount'].sum().reset_index()
        fig_inflow = px.line(
            tx_monthly, x='month', y='amount', color='transaction_type',
            labels={'month': 'Year-Month', 'amount': 'Total Amount (₹)', 'transaction_type': 'Type'},
            markers=True,
            color_discrete_sequence=['#3b82f6', '#f59e0b']
        )
        fig_inflow.update_layout(template="plotly_white", margin=dict(t=10))
        st.plotly_chart(fig_inflow, use_container_width=True)
    else:
        st.info("No transaction data available.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — FUND PERFORMANCE SCORECARD
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📈 Fund Performance Scorecard":
    page_banner("📈 Fund Performance Scorecard",
                "Detailed return & risk analytics with interactive fund filters")

    if perf_data.empty:
        st.warning("Performance data not available. Please run compute_metrics.py first.")
    else:
        # ── Filters ───────────────────────────────────────────────────────────
        section_title("Filter Schemes")
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            fund_houses = ["All"] + sorted(perf_data['fund_house'].dropna().unique().tolist())
            selected_fh = st.selectbox("Select Fund House", fund_houses)
        with filter_col2:
            categories = ["All"] + sorted(perf_data['scheme_category'].dropna().unique().tolist())
            selected_cat = st.selectbox("Select Scheme Category", categories)

        filtered_perf = perf_data.copy()
        if selected_fh != "All":
            filtered_perf = filtered_perf[filtered_perf['fund_house'] == selected_fh]
        if selected_cat != "All":
            filtered_perf = filtered_perf[filtered_perf['scheme_category'] == selected_cat]

        st.write("")

        if filtered_perf.empty:
            st.warning("No schemes match the selected filters.")
        else:
            # ── Performance Table ──────────────────────────────────────────────
            section_title("Performance Analytics Table")
            display_cols = {
                'scheme_name': 'Scheme Name',
                'scheme_category': 'Category',
                'return_1y': '1Y Return (%)',
                'return_3y': '3Y Return (%)',
                'return_5y': '5Y Return (%)',
                'volatility': 'Volatility (%)',
                'sharpe_ratio': 'Sharpe Ratio'
            }
            # Only include columns that exist
            available_cols = {k: v for k, v in display_cols.items() if k in filtered_perf.columns}
            table_df = filtered_perf[list(available_cols.keys())].rename(columns=available_cols)
            fmt = {}
            for col in ['1Y Return (%)', '3Y Return (%)', '5Y Return (%)', 'Volatility (%)']:
                if col in table_df.columns:
                    fmt[col] = '{:.2f}%'
            if 'Sharpe Ratio' in table_df.columns:
                fmt['Sharpe Ratio'] = '{:.4f}'
            st.dataframe(table_df.style.format(fmt), use_container_width=True)

            # ── Risk vs Return Scatter ─────────────────────────────────────────
            section_title("Risk vs Return Analysis (Color = Sharpe Ratio)")
            req_cols = ['return_1y', 'volatility', 'sharpe_ratio', 'scheme_name']
            if all(c in filtered_perf.columns for c in req_cols):
                fig_scatter = px.scatter(
                    filtered_perf,
                    x='return_1y', y='volatility',
                    color='sharpe_ratio',
                    hover_name='scheme_name',
                    hover_data={'return_1y': ':.2f', 'volatility': ':.2f', 'sharpe_ratio': ':.4f'},
                    labels={
                        'return_1y': '1Y Return (%)',
                        'volatility': 'Volatility (%)',
                        'sharpe_ratio': 'Sharpe Ratio'
                    },
                    color_continuous_scale='viridis'
                )
                fig_scatter.update_traces(marker=dict(size=16, line=dict(width=1, color='white')))
                fig_scatter.update_layout(template="plotly_white", margin=dict(t=10))
                st.plotly_chart(fig_scatter, use_container_width=True)
            else:
                st.info("Required columns for scatter plot are not available.")

            # ── Historical NAV Viewer ──────────────────────────────────────────
            section_title("Historical NAV Trend Viewer")
            scheme_options = filtered_perf['scheme_name'].unique().tolist()
            if scheme_options and not nav_data.empty:
                selected_scheme = st.selectbox("Select Scheme for NAV Timeline", scheme_options)
                scheme_nav = nav_data[nav_data['scheme_name'] == selected_scheme]
                if not scheme_nav.empty:
                    fig_nav = px.line(
                        scheme_nav, x='calendar_date', y='nav',
                        labels={'calendar_date': 'Date', 'nav': 'NAV (₹)'},
                        title=f"NAV Trend — {selected_scheme.split(' - ')[0]}",
                        color_discrete_sequence=['#3b82f6']
                    )
                    fig_nav.update_layout(template="plotly_white", margin=dict(t=40))
                    fig_nav.update_traces(line=dict(width=2))
                    st.plotly_chart(fig_nav, use_container_width=True)
                else:
                    st.info(f"No NAV data found for: {selected_scheme}")
            else:
                st.info("No NAV data available.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — INVESTOR DEMOGRAPHICS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "👥 Investor Demographics":
    page_banner("👥 Investor Demographics & Transaction Analytics",
                "Age groups, regional inflows, SIP vs Lumpsum preferences, and registration trends")

    col1, col2 = st.columns(2)
    with col1:
        section_title("Top 10 States by Transaction Inflows")
        # 'state' now comes from LEFT JOIN with dim_investor in load_fact_transactions
        if not tx_data.empty and 'state' in tx_data.columns:
            state_inflows = (
                tx_data.dropna(subset=['state'])
                .groupby('state')['amount'].sum()
                .reset_index()
                .sort_values('amount', ascending=False)
            )
            if not state_inflows.empty:
                fig_state = px.bar(
                    state_inflows.head(10),
                    x='amount', y='state', orientation='h',
                    labels={'amount': 'Total Inflows (\u20b9)', 'state': 'State'},
                    color='amount',
                    color_continuous_scale='Blues'
                )
                fig_state.update_layout(showlegend=False, template="plotly_white",
                                        coloraxis_showscale=False, margin=dict(t=10))
                st.plotly_chart(fig_state, use_container_width=True)
            else:
                st.info("State data not available in transactions.")
        else:
            st.info("State data not available.")

    with col2:
        section_title("SIP vs Lumpsum Split")
        if not tx_data.empty and 'transaction_type' in tx_data.columns:
            type_split = tx_data.groupby('transaction_type')['amount'].sum().reset_index()
            fig_type = px.pie(
                type_split, values='amount', names='transaction_type',
                hole=0.42,
                color_discrete_sequence=['#3b82f6', '#f59e0b']
            )
            fig_type.update_layout(template="plotly_white", margin=dict(t=10))
            fig_type.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_type, use_container_width=True)
        else:
            st.info("Transaction type data not available.")

    st.write("")

    col3, col4 = st.columns(2)
    with col3:
        section_title("Average SIP Amount by Age Group")
        if not investors.empty and 'age_group' in investors.columns and 'sip_amount' in investors.columns:
            age_sip = investors.groupby('age_group')['sip_amount'].mean().reset_index()
            fig_age = px.bar(
                age_sip, x='age_group', y='sip_amount',
                labels={'age_group': 'Age Group', 'sip_amount': 'Avg SIP Amount (\u20b9)'},
                color='sip_amount',
                color_continuous_scale='Teal'
            )
            fig_age.update_layout(showlegend=False, template="plotly_white",
                                  coloraxis_showscale=False, margin=dict(t=10))
            st.plotly_chart(fig_age, use_container_width=True)
        else:
            st.info("Age group or SIP data not available.")

    with col4:
        section_title("Monthly Investor Registrations")
        if not investors.empty and 'registration_date' in investors.columns:
            investors_copy = investors.copy()
            investors_copy['reg_date'] = pd.to_datetime(investors_copy['registration_date'], errors='coerce')
            investors_copy = investors_copy.dropna(subset=['reg_date'])
            reg_monthly = (
                investors_copy.groupby(investors_copy['reg_date'].dt.to_period('M'))['investor_id']
                .count()
                .reset_index()
            )
            reg_monthly['reg_date'] = reg_monthly['reg_date'].astype(str)
            fig_reg = px.line(
                reg_monthly, x='reg_date', y='investor_id',
                labels={'reg_date': 'Month', 'investor_id': 'New Registrations'},
                markers=True,
                color_discrete_sequence=['#10b981']
            )
            fig_reg.update_layout(template="plotly_white", margin=dict(t=10))
            fig_reg.update_traces(line=dict(width=2))
            st.plotly_chart(fig_reg, use_container_width=True)
        else:
            st.info("Registration date data not available.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — SIP CONTINUITY & GAPS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚠️ SIP Continuity & Gaps":
    page_banner("⚠️ SIP Continuity & Cohort Gaps Analysis",
                "Investor cohort behavior, SIP transaction gaps, and at-risk flagging")

    # ── Cohort Analysis ───────────────────────────────────────────────────────
    section_title("Investor Cohort Analysis by Registration Year")
    if not investors.empty and not tx_data.empty:
        investors_copy = investors.copy()
        investors_copy['reg_year'] = pd.to_datetime(
            investors_copy['registration_date'], errors='coerce'
        ).dt.year
        cohort_tx = tx_data.merge(
            investors_copy[['investor_id', 'reg_year', 'sip_amount']],
            on='investor_id', how='inner'
        )
        if not cohort_tx.empty:
            cohort_summary = cohort_tx.groupby('reg_year').agg(
                Avg_SIP_Amount=('sip_amount', 'mean'),
                Total_Invested=('amount', 'sum'),
                Total_Investors=('investor_id', 'nunique')
            ).reset_index()
            cohort_summary.columns = ['Registration Year', 'Avg SIP Amount (₹)', 'Total Invested (₹)', 'Unique Investors']

            col_tbl, col_chart = st.columns([1, 1])
            with col_tbl:
                st.dataframe(
                    cohort_summary.style.format({
                        'Avg SIP Amount (₹)': '₹{:,.2f}',
                        'Total Invested (₹)': '₹{:,.0f}'
                    }),
                    use_container_width=True
                )
            with col_chart:
                fig_cohort = px.bar(
                    cohort_summary, x='Registration Year', y='Total Invested (\u20b9)',
                    color='Unique Investors',
                    color_continuous_scale='Purples',
                    labels={'Registration Year': 'Cohort Year'}
                )
                fig_cohort.update_layout(template="plotly_white",
                                         coloraxis_showscale=False, margin=dict(t=10))
                st.plotly_chart(fig_cohort, use_container_width=True)
        else:
            st.info("No matching investor-transaction data for cohort analysis.")
    else:
        st.info("Investor or transaction data not available.")

    st.write("")

    # ── SIP Gap Analysis ──────────────────────────────────────────────────────
    section_title("SIP Gaps Analysis & At-Risk Investor Flagger")
    if not tx_data.empty and 'transaction_type' in tx_data.columns:
        sip_txns = tx_data[tx_data['transaction_type'] == 'SIP'].copy()
        if sip_txns.empty:
            st.info("No SIP transactions found.")
        else:
            sip_counts = sip_txns.groupby('investor_id').size()
            eligible_investors = sip_counts[sip_counts >= 6].index

            if len(eligible_investors) == 0:
                st.info("No investors with 6+ SIP transactions found.")
            else:
                gap_data = []
                for inv_id in eligible_investors:
                    inv_sip = sip_txns[sip_txns['investor_id'] == inv_id].sort_values('calendar_date')
                    gaps = inv_sip['calendar_date'].diff().dt.days.dropna()
                    if len(gaps) == 0:
                        continue
                    avg_gap = gaps.mean()
                    gap_data.append({
                        "Investor ID": inv_id,
                        "SIP Count": len(inv_sip),
                        "Avg Gap (Days)": round(avg_gap, 1),
                        "Status": "At-Risk (Gap > 35d)" if avg_gap > 35 else "Continuous"
                    })

                gap_df = pd.DataFrame(gap_data)
                at_risk_df = gap_df[gap_df['Status'] == "At-Risk (Gap > 35d)"]

                m1, m2, m3 = st.columns(3)
                with m1:
                    st.markdown(f"""
                        <div class='kpi-card'>
                            <div class='kpi-title'>Investors Analyzed</div>
                            <div class='kpi-value'>{len(gap_df)}</div>
                            <div class='kpi-sub'>With 6+ SIP transactions</div>
                        </div>
                    """, unsafe_allow_html=True)
                with m2:
                    st.markdown(f"""
                        <div class='kpi-card' style='border-bottom:4px solid #ef4444;'>
                            <div class='kpi-title'>At-Risk Investors</div>
                            <div class='kpi-value'>{len(at_risk_df)}</div>
                            <div class='kpi-sub'>Avg gap &gt; 35 days</div>
                        </div>
                    """, unsafe_allow_html=True)
                with m3:
                    pct = len(at_risk_df) / len(gap_df) * 100 if len(gap_df) > 0 else 0
                    st.markdown(f"""
                        <div class='kpi-card' style='border-bottom:4px solid #f59e0b;'>
                            <div class='kpi-title'>At-Risk Rate</div>
                            <div class='kpi-value'>{pct:.1f}%</div>
                            <div class='kpi-sub'>of analyzed investors</div>
                        </div>
                    """, unsafe_allow_html=True)

                st.write("")

                def highlight_status(val):
                    if val == "At-Risk (Gap > 35d)":
                        return 'background-color: #fee2e2; color: #991b1b; font-weight:600;'
                    return 'background-color: #dcfce7; color: #166534; font-weight:600;'

                st.dataframe(
                    gap_df.style.map(highlight_status, subset=['Status']),
                    use_container_width=True
                )
    else:
        st.info("Transaction data not available.")

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5 — ADVANCED ANALYTICS & RECOMMENDER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔮 Advanced Analytics & Recommender":
    page_banner("🔮 Advanced Financial Analytics & Portfolio Optimizer",
                "Tail risk (VaR/CVaR), Monte Carlo simulations, Markowitz Frontier, and AI recommender")

    if nav_data.empty:
        st.error("NAV data not available. Cannot run advanced analytics.")
        st.stop()

    # Build return series (shared across tabs)
    nav_pivot = nav_data.pivot(index="calendar_date", columns="scheme_name", values="nav").sort_index()
    returns = nav_pivot.pct_change().dropna(how="all")
    scheme_names = list(returns.columns)

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🛡️ Tail Risk (VaR / CVaR)",
        "📈 Rolling Sharpe Ratio",
        "🎲 Monte Carlo Simulation",
        "🎯 Efficient Frontier",
        "🤖 Fund Recommender"
    ])

    # ── Tab 1: VaR / CVaR ────────────────────────────────────────────────────
    with tab1:
        section_title("95% Daily Historical VaR & Conditional VaR (CVaR)")
        var_rows = []
        for col in scheme_names:
            ret = returns[col].dropna()
            if len(ret) < 30:
                continue
            var_95  = np.percentile(ret, 5)
            cvar_95 = ret[ret <= var_95].mean()
            var_rows.append({
                "Scheme": col.split(" - ")[0],
                "Full Name": col,
                "95% VaR (Daily)": f"{var_95*100:.4f}%",
                "95% CVaR (Daily)": f"{cvar_95*100:.4f}%",
                "VaR Annualized": f"{var_95 * np.sqrt(252) * 100:.2f}%"
            })

        if var_rows:
            st.dataframe(pd.DataFrame(var_rows), use_container_width=True)
        else:
            st.info("Insufficient data to compute VaR.")

        st.write("")
        section_title("Daily Return Distribution")
        hist_scheme = st.selectbox("Select Scheme for Return Distribution", scheme_names,
                                   key="hist_scheme")
        ret_series = returns[hist_scheme].dropna() * 100
        var_line   = np.percentile(returns[hist_scheme].dropna(), 5) * 100

        fig_hist = px.histogram(
            ret_series, nbins=100,
            labels={'value': 'Daily Return (%)'},
            color_discrete_sequence=['#3b82f6']
        )
        fig_hist.add_vline(x=var_line, line_dash="dash", line_color="#ef4444",
                           annotation_text=f"VaR 95%: {var_line:.3f}%",
                           annotation_position="top right")
        fig_hist.update_layout(template="plotly_white", showlegend=False,
                               title=f"Return Distribution — {hist_scheme.split(' - ')[0]}",
                               margin=dict(t=40))
        st.plotly_chart(fig_hist, use_container_width=True)

    # ── Tab 2: Rolling Sharpe ─────────────────────────────────────────────────
    with tab2:
        section_title("Rolling 90-Day Sharpe Ratio")
        RF_daily = 0.065 / 252
        rolling_sharpe_df = pd.DataFrame(index=returns.index)
        for col in scheme_names:
            mean_90 = returns[col].rolling(90).mean()
            std_90  = returns[col].rolling(90).std()
            rolling_sharpe_df[col] = ((mean_90 - RF_daily) / std_90.replace(0, np.nan)) * np.sqrt(252)

        rolling_sharpe_clean = rolling_sharpe_df.dropna(how="all").reset_index()

        selected_funds = st.multiselect(
            "Select Funds to Plot", scheme_names,
            default=scheme_names[:3],
            key="rolling_funds"
        )
        if selected_funds:
            fig_rolling = px.line(
                rolling_sharpe_clean, x='calendar_date', y=selected_funds,
                labels={'calendar_date': 'Date', 'value': '90-Day Sharpe Ratio', 'variable': 'Scheme'},
                title="Rolling 90-Day Sharpe Ratio"
            )
            fig_rolling.add_hline(y=0, line_dash="dot", line_color="#94a3b8",
                                  annotation_text="Sharpe = 0")
            fig_rolling.update_layout(template="plotly_white", margin=dict(t=40))
            st.plotly_chart(fig_rolling, use_container_width=True)
        else:
            st.info("Select at least one fund to plot.")

    # ── Tab 3: Monte Carlo ────────────────────────────────────────────────────
    with tab3:
        section_title("5-Year NAV Growth Projections via Monte Carlo")
        mc_scheme = st.selectbox("Select Scheme for Simulation", scheme_names, key="mc_scheme")
        n_sims_choice = st.slider("Number of Simulations", 500, 2000, 1000, step=250)

        if st.button("▶ Run Monte Carlo Simulation", key="mc_btn"):
            with st.spinner("Running simulations..."):
                fund_ret    = returns[mc_scheme].dropna()
                log_returns = np.log(1 + fund_ret)
                mu          = log_returns.mean()
                var_        = log_returns.var()
                drift       = mu - (0.5 * var_)
                std_dev     = log_returns.std()

                n_sim_days = 5 * 252
                S0 = nav_pivot[mc_scheme].dropna().iloc[-1]

                np.random.seed(42)
                shocks = np.random.normal(0, 1, (n_sim_days, n_sims_choice))
                daily_sim_returns = np.exp(drift + std_dev * shocks)

                paths    = np.zeros_like(daily_sim_returns)
                paths[0] = S0 * daily_sim_returns[0]
                for t in range(1, n_sim_days):
                    paths[t] = paths[t-1] * daily_sim_returns[t]

                time_index = pd.date_range(start=nav_pivot.index[-1], periods=n_sim_days, freq="B")
                p10 = np.percentile(paths, 10, axis=1)
                p50 = np.percentile(paths, 50, axis=1)
                p90 = np.percentile(paths, 90, axis=1)

                fig_mc = go.Figure()
                for i in range(min(20, n_sims_choice)):
                    fig_mc.add_trace(go.Scatter(
                        x=time_index, y=paths[:, i], mode='lines',
                        line=dict(color='rgba(59, 130, 246, 0.08)'), showlegend=False
                    ))
                fig_mc.add_trace(go.Scatter(x=time_index, y=p90, mode='lines',
                                            line=dict(width=0), showlegend=False))
                fig_mc.add_trace(go.Scatter(
                    x=time_index, y=p10, mode='lines',
                    fill='tonexty', fillcolor='rgba(59, 130, 246, 0.12)',
                    name='80% Confidence Band', line=dict(width=0)
                ))
                fig_mc.add_trace(go.Scatter(
                    x=time_index, y=p50, mode='lines',
                    name='Median (50th %ile)', line=dict(color='#0f172a', width=2.5)
                ))
                fig_mc.update_layout(
                    title=f"Monte Carlo 5-Year Projection — {mc_scheme.split(' - ')[0]}",
                    xaxis_title="Date", yaxis_title="Projected NAV (₹)",
                    template="plotly_white", margin=dict(t=50)
                )
                st.plotly_chart(fig_mc, use_container_width=True)

                # Summary stats
                final_navs = paths[-1, :]
                sc1, sc2, sc3 = st.columns(3)
                with sc1:
                    st.metric("Median Final NAV", f"₹{np.median(final_navs):,.2f}",
                              delta=f"{((np.median(final_navs)/S0)-1)*100:+.1f}% vs today")
                with sc2:
                    st.metric("Best Case (90th %ile)", f"₹{np.percentile(final_navs, 90):,.2f}")
                with sc3:
                    st.metric("Worst Case (10th %ile)", f"₹{np.percentile(final_navs, 10):,.2f}")
        else:
            st.markdown("<div class='info-box'>Click the button above to run the simulation.</div>",
                        unsafe_allow_html=True)

    # ── Tab 4: Efficient Frontier ─────────────────────────────────────────────
    with tab4:
        section_title("Markowitz Efficient Frontier Portfolio Optimization")

        # Auto-detect available fund names from DB (robust — no hardcoding)
        available_schemes = sorted(scheme_names)
        default_selection = available_schemes[:5] if len(available_schemes) >= 5 else available_schemes

        frontier_funds = st.multiselect(
            "Select 2–8 funds for portfolio optimization",
            available_schemes, default=default_selection, key="ef_funds"
        )

        if len(frontier_funds) < 2:
            st.warning("Please select at least 2 funds for the Efficient Frontier simulation.")
        elif st.button("▶ Simulate 5,000 Portfolios", key="ef_btn"):
            with st.spinner("Optimizing portfolios..."):
                sel_returns  = returns[frontier_funds].dropna()
                ann_returns  = sel_returns.mean() * 252
                cov_matrix   = sel_returns.cov() * 252
                n_funds      = len(frontier_funds)
                num_portfolios = 5000

                results         = np.zeros((3, num_portfolios))
                weights_record  = []

                np.random.seed(42)
                for i in range(num_portfolios):
                    w = np.random.random(n_funds)
                    w /= w.sum()
                    weights_record.append(w)
                    port_ret   = np.sum(w * ann_returns)
                    port_std   = np.sqrt(np.dot(w.T, np.dot(cov_matrix, w)))
                    port_sharpe = (port_ret - 0.065) / port_std if port_std > 0 else 0
                    results[0, i] = port_ret
                    results[1, i] = port_std
                    results[2, i] = port_sharpe

                max_sharpe_idx = np.argmax(results[2])
                min_vol_idx    = np.argmin(results[1])
                weights_msr    = weights_record[max_sharpe_idx]
                weights_mvp    = weights_record[min_vol_idx]

                fig_ef = px.scatter(
                    x=results[1] * 100, y=results[0] * 100, color=results[2],
                    labels={'x': 'Volatility (%)', 'y': 'Expected Return (%)', 'color': 'Sharpe'},
                    color_continuous_scale='viridis',
                    opacity=0.6
                )
                fig_ef.add_trace(go.Scatter(
                    x=[results[1, max_sharpe_idx] * 100], y=[results[0, max_sharpe_idx] * 100],
                    mode='markers', marker=dict(symbol='star', size=18, color='#ef4444'),
                    name='Max Sharpe (MSR)'
                ))
                fig_ef.add_trace(go.Scatter(
                    x=[results[1, min_vol_idx] * 100], y=[results[0, min_vol_idx] * 100],
                    mode='markers', marker=dict(symbol='star', size=18, color='#3b82f6'),
                    name='Min Volatility (MVP)'
                ))
                fig_ef.update_layout(template="plotly_white",
                                     title="Markowitz Efficient Frontier (5,000 Portfolios)",
                                     margin=dict(t=50))
                st.plotly_chart(fig_ef, use_container_width=True)

                col_msr, col_mvp = st.columns(2)
                with col_msr:
                    st.markdown("**🔴 Max Sharpe Portfolio (MSR)**")
                    msr_df = pd.DataFrame({
                        "Fund": [f.split(' - ')[0] for f in frontier_funds],
                        "Weight (%)": [f"{w*100:.2f}%" for w in weights_msr]
                    })
                    st.dataframe(msr_df, use_container_width=True)
                    st.metric("Sharpe Ratio", f"{results[2, max_sharpe_idx]:.4f}")
                with col_mvp:
                    st.markdown("**🔵 Min Volatility Portfolio (MVP)**")
                    mvp_df = pd.DataFrame({
                        "Fund": [f.split(' - ')[0] for f in frontier_funds],
                        "Weight (%)": [f"{w*100:.2f}%" for w in weights_mvp]
                    })
                    st.dataframe(mvp_df, use_container_width=True)
                    st.metric("Volatility", f"{results[1, min_vol_idx]*100:.2f}%")
        else:
            st.markdown("<div class='info-box'>Select your funds above, then click Simulate.</div>",
                        unsafe_allow_html=True)

    # ── Tab 5: Fund Recommender ───────────────────────────────────────────────
    with tab5:
        section_title("Risk Appetite-Based Fund Recommender")

        st.markdown("""
            <div class='info-box'>
                This engine maps your risk appetite to fund categories and ranks them by Sharpe Ratio.
            </div>
        """, unsafe_allow_html=True)
        st.write("")

        risk_input = st.radio(
            "Select your Risk Appetite:",
            ["🟢 Low — Stable returns, capital preservation (Debt / Money Market)",
             "🟡 Moderate — Balanced growth (Large Cap / ELSS / Tax Saver)",
             "🔴 High — Maximum growth potential (Mid Cap / Small Cap)"],
            key="risk_radio"
        )

        if st.button("🤖 Generate Fund Recommendations", key="rec_btn"):
            if "Low" in risk_input:
                risk_level = "Low"
            elif "Moderate" in risk_input:
                risk_level = "Moderate"
            else:
                risk_level = "High"

            def cat_to_risk(cat):
                cat_lower = str(cat).lower()
                if any(k in cat_lower for k in ["debt", "money market", "liquid", "gilt"]):
                    return "Low"
                elif any(k in cat_lower for k in ["large cap", "elss", "tax", "flexi"]):
                    return "Moderate"
                else:
                    return "High"

            if perf_data.empty:
                st.error("Performance data not available.")
            else:
                rec_df = perf_data.copy()
                rec_df["Risk Grade"] = rec_df["scheme_category"].apply(cat_to_risk)
                matched = rec_df[rec_df["Risk Grade"] == risk_level].sort_values(
                    "sharpe_ratio", ascending=False
                )

                if matched.empty:
                    st.warning(f"No funds found matching the **{risk_level}** risk profile.")
                else:
                    st.success(f"Found {len(matched)} fund(s) matching your **{risk_level}** risk profile:")
                    display = matched[['scheme_name', 'scheme_category',
                                       'return_1y', 'volatility', 'sharpe_ratio']].copy()
                    display.columns = ['Scheme Name', 'Category',
                                       '1Y Return (%)', 'Volatility (%)', 'Sharpe Ratio']
                    st.dataframe(
                        display.style.format({
                            '1Y Return (%)': '{:.2f}%',
                            'Volatility (%)': '{:.2f}%',
                            'Sharpe Ratio': '{:.4f}'
                        }),
                        use_container_width=True
                    )
        else:
            st.markdown("<div class='info-box'>Select your risk appetite and click Generate Recommendations.</div>",
                        unsafe_allow_html=True)
