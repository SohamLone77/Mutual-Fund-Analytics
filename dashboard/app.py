import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as ob
import matplotlib.pyplot as plt
from pathlib import Path

# Set page configuration
st.set_page_config(
    page_title="Mutual Fund Analytics | Bluestock Fintech",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling for Premium Aesthetics
st.markdown("""
    <style>
    /* Main body background and text */
    .stApp {
        background-color: #f8fafc;
        color: #1e293b;
        font-family: 'Poppins', sans-serif;
    }
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #0f172a;
    }
    section[data-testid="stSidebar"] .stMarkdown {
        color: #f1f5f9;
    }
    /* KPI Card styling */
    .kpi-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05);
        border-bottom: 4px solid #38bdf8;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
    }
    .kpi-title {
        font-size: 14px;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        margin-bottom: 8px;
    }
    .kpi-value {
        font-size: 28px;
        font-weight: 800;
        color: #0f172a;
    }
    </style>
""", unsafe_allowed_html=True)

# Database Connection Helper
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "db" / "bluestock_mf.db"

@st.cache_resource
def get_connection():
    if not DB_PATH.exists():
        st.error(f"SQLite Database not found at: {DB_PATH}")
        return None
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)

conn = get_connection()

# Load Core Data
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

# Load variables
dim_funds = load_dim_funds()
perf_data = load_fact_performance()
aum_data = load_fact_aum()
nav_data = load_fact_nav()
tx_data = load_fact_transactions()
investors = load_dim_investors()
nifty = load_nifty50()

# Sidebar Navigation Panel
st.sidebar.markdown("<h2 style='color:#38bdf8; text-align:center;'>Bluestock Fintech</h2>", unsafe_allowed_html=True)
st.sidebar.markdown("<p style='color:#94a3b8; text-align:center; font-size:14px;'>Mutual Fund Analytics Dashboard</p>", unsafe_allowed_html=True)
st.sidebar.write("---")

page = st.sidebar.radio(
    "Go To Page",
    ["📊 Industry & AUM Overview",
     "📈 Fund Performance Scorecard",
     "👥 Investor Demographics",
     "⚠️ SIP Continuity & Gaps",
     "🔮 Advanced Analytics & Recommender"]
)

# ----------------- PAGE 1: INDUSTRY & AUM OVERVIEW -----------------
if page == "📊 Industry & AUM Overview":
    st.title("Mutual Fund Industry & AUM Overview")
    st.write("Overview of assets under management (AUM) and broad industry indicators.")
    st.write("---")

    # KPI Summary Row
    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    with kpi_col1:
        st.markdown("""
            <div class='kpi-card'>
                <div class='kpi-title'>Total Tracked AUM</div>
                <div class='kpi-value'>₹488.1 Cr</div>
            </div>
        """, unsafe_allowed_html=True)
    with kpi_col2:
        st.markdown("""
            <div class='kpi-card' style='border-bottom: 4px solid #10b981;'>
                <div class='kpi-title'>Tracked Folios</div>
                <div class='kpi-value'>250</div>
            </div>
        """, unsafe_allowed_html=True)
    with kpi_col3:
        st.markdown("""
            <div class='kpi-card' style='border-bottom: 4px solid #f59e0b;'>
                <div class='kpi-title'>Total Transactions</div>
                <div class='kpi-value'>4,224</div>
            </div>
        """, unsafe_allowed_html=True)
    with kpi_col4:
        st.markdown("""
            <div class='kpi-card' style='border-bottom: 4px solid #ec4899;'>
                <div class='kpi-title'>Tracked Schemes</div>
                <div class='kpi-value'>6</div>
            </div>
        """, unsafe_allowed_html=True)

    st.write("")
    st.write("")

    # Visualizations layout
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Asset Allocation (AUM Value in ₹ Cr)")
        # Plotly Bar Chart
        if not aum_data.empty:
            aum_clean = aum_data.copy()
            aum_clean['scheme_short'] = aum_clean['scheme_name'].apply(lambda x: x.split(" - ")[0])
            fig_aum = px.bar(
                aum_clean,
                x='scheme_short',
                y='aum_value',
                labels={'scheme_short': 'Scheme Name', 'aum_value': 'AUM Value (₹ Cr)'},
                color='scheme_short',
                color_discrete_sequence=px.colors.qualitative.Plotly
            )
            fig_aum.update_layout(showlegend=False, template="plotly_white")
            st.plotly_chart(fig_aum, use_container_width=True)

    with col2:
        st.subheader("AUM Distribution by Category")
        if not aum_data.empty:
            fig_pie = px.pie(
                aum_data,
                values='aum_value',
                names='scheme_category',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Safe
            )
            fig_pie.update_layout(template="plotly_white")
            st.plotly_chart(fig_pie, use_container_width=True)

    # Monthly Inflow time series chart
    st.subheader("Monthly Transaction Amounts Over Time")
    if not tx_data.empty:
        tx_grouped = tx_data.copy()
        tx_grouped['month'] = tx_grouped['calendar_date'].dt.to_period('M').astype(str)
        tx_monthly = tx_grouped.groupby(['month', 'transaction_type'])['amount'].sum().reset_index()
        
        fig_inflow = px.line(
            tx_monthly,
            x='month',
            y='amount',
            color='transaction_type',
            labels={'month': 'Year-Month', 'amount': 'Total Inflow Amount (₹)', 'transaction_type': 'Type'},
            markers=True
        )
        fig_inflow.update_layout(template="plotly_white")
        st.plotly_chart(fig_inflow, use_container_width=True)

# ----------------- PAGE 2: FUND PERFORMANCE SCORECARD -----------------
elif page == "📈 Fund Performance Scorecard":
    st.title("Mutual Fund Performance Scorecard")
    st.write("Detailed return and risk analytics with interactive parameter filters.")
    st.write("---")

    # Filters
    st.subheader("Filter Schemes")
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        fund_houses = ["All"] + list(perf_data['fund_house'].unique())
        selected_fh = st.selectbox("Select Fund House", fund_houses)
    with filter_col2:
        categories = ["All"] + list(perf_data['scheme_category'].unique())
        selected_cat = st.selectbox("Select Scheme Category", categories)

    # Apply Filters
    filtered_perf = perf_data.copy()
    if selected_fh != "All":
        filtered_perf = filtered_perf[filtered_perf['fund_house'] == selected_fh]
    if selected_cat != "All":
        filtered_perf = filtered_perf[filtered_perf['scheme_category'] == selected_cat]

    st.write("")

    # Display main performance table
    st.subheader("Performance Analytics Table")
    display_cols = {
        'scheme_name': 'Scheme Name',
        'scheme_category': 'Category',
        'return_1y': '1Y Return (%)',
        'return_3y': '3Y Return (%)',
        'return_5y': '5Y Return (%)',
        'volatility': 'Volatility (%)',
        'sharpe_ratio': 'Sharpe Ratio'
    }
    table_df = filtered_perf[list(display_cols.keys())].rename(columns=display_cols)
    st.dataframe(table_df.style.format({
        '1Y Return (%)': '{:.2f}%',
        '3Y Return (%)': '{:.2f}%',
        '5Y Return (%)': '{:.2f}%',
        'Volatility (%)': '{:.2f}%',
        'Sharpe Ratio': '{:.4f}'
    }), use_container_width=True)

    # Scatter plot: Risk vs Return
    st.subheader("Risk vs Return Analysis")
    if not filtered_perf.empty:
        fig_scatter = px.scatter(
            filtered_perf,
            x='return_1y',
            y='volatility',
            size='sharpe_ratio',
            color='scheme_name',
            hover_name='scheme_name',
            labels={'return_1y': 'Annualized Return (%)', 'volatility': 'Annualized Volatility (%)'},
            size_max=30
        )
        fig_scatter.update_layout(template="plotly_white")
        st.plotly_chart(fig_scatter, use_container_width=True)

    # Interactive historical NAV line chart
    st.subheader("Historical NAV Trend Viewer")
    selected_scheme = st.selectbox("Select Scheme for NAV Timeline", perf_data['scheme_name'].unique())
    if not nav_data.empty:
        scheme_nav = nav_data[nav_data['scheme_name'] == selected_scheme]
        fig_nav = px.line(
            scheme_nav,
            x='calendar_date',
            y='nav',
            labels={'calendar_date': 'Date', 'nav': 'Net Asset Value (NAV)'},
            title=f"NAV Trend — {selected_scheme.split(' - ')[0]}"
        )
        fig_nav.update_layout(template="plotly_white")
        st.plotly_chart(fig_nav, use_container_width=True)

# ----------------- PAGE 3: INVESTOR DEMOGRAPHICS -----------------
elif page == "👥 Investor Demographics":
    st.title("Investor Demographics & Transaction Analytics")
    st.write("Understand investor age groups, regions, and investment type preferences.")
    st.write("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Transaction Inflows by State")
        if not tx_data.empty:
            state_inflows = tx_data.groupby('state')['amount'].sum().reset_index().sort_values('amount', ascending=False)
            fig_state = px.bar(
                state_inflows.head(10),
                x='amount',
                y='state',
                orientation='h',
                labels={'amount': 'Total Inflows (₹)', 'state': 'State'},
                color='state'
            )
            fig_state.update_layout(showlegend=False, template="plotly_white")
            st.plotly_chart(fig_state, use_container_width=True)

    with col2:
        st.subheader("Investment Type Share (SIP vs Lumpsum)")
        if not tx_data.empty:
            type_split = tx_data.groupby('transaction_type')['amount'].sum().reset_index()
            fig_type = px.pie(
                type_split,
                values='amount',
                names='transaction_type',
                hole=0.4,
                color_discrete_sequence=['#4154f1', '#F05537']
            )
            fig_type.update_layout(template="plotly_white")
            st.plotly_chart(fig_type, use_container_width=True)

    st.write("")
    
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Average SIP Amount by Age Group")
        if not investors.empty:
            age_sip = investors.groupby('age_group')['sip_amount'].mean().reset_index()
            fig_age = px.bar(
                age_sip,
                x='age_group',
                y='sip_amount',
                labels={'age_group': 'Age Group', 'sip_amount': 'Average SIP Amount (₹)'},
                color='age_group'
            )
            fig_age.update_layout(showlegend=False, template="plotly_white")
            st.plotly_chart(fig_age, use_container_width=True)
            
    with col4:
        st.subheader("Investor Registration Trend")
        if not investors.empty:
            investors['reg_date'] = pd.to_datetime(investors['registration_date'])
            reg_monthly = investors.groupby(investors['reg_date'].dt.to_period('M'))['investor_id'].count().reset_index()
            reg_monthly['reg_date'] = reg_monthly['reg_date'].astype(str)
            fig_reg = px.line(
                reg_monthly,
                x='reg_date',
                y='investor_id',
                labels={'reg_date': 'Month', 'investor_id': 'New Registrations'},
                markers=True
            )
            fig_reg.update_layout(template="plotly_white")
            st.plotly_chart(fig_reg, use_container_width=True)

# ----------------- PAGE 4: SIP CONTINUITY & GAPS -----------------
elif page == "⚠️ SIP Continuity & Gaps":
    st.title("SIP Continuity & Cohort Gaps Analysis")
    st.write("Monitor transaction behavior, gap timings, and cohort performance indicators.")
    st.write("---")

    # Cohort Analysis (Group by first transaction year / registration year)
    st.subheader("Investor Cohort Analysis")
    if not investors.empty and not tx_data.empty:
        investors['reg_year'] = pd.to_datetime(investors['registration_date']).dt.year
        cohort_tx = tx_data.merge(investors, on='investor_id', how='inner')
        cohort_summary = cohort_tx.groupby('reg_year').agg(
            Avg_SIP_Amount=('sip_amount', 'mean'),
            Total_Invested=('amount', 'sum'),
            Total_Investors=('investor_id', 'nunique')
        ).reset_index()
        st.dataframe(cohort_summary.style.format({
            'Avg_SIP_Amount': '₹{:.2f}',
            'Total_Invested': '₹{:,.2f}'
        }), use_container_width=True)

    st.write("")

    # SIP gaps and Flag at-risk investors
    st.subheader("SIP Gaps Analysis & At-Risk Flagger")
    if not tx_data.empty:
        sip_txns = tx_data[tx_data['transaction_type'] == 'SIP'].copy()
        sip_counts = sip_txns.groupby('investor_id').size()
        eligible_investors = sip_counts[sip_counts >= 6].index

        gap_data = []
        for inv_id in eligible_investors:
            inv_sip = sip_txns[sip_txns['investor_id'] == inv_id].sort_values('calendar_date')
            gaps = inv_sip['calendar_date'].diff().dt.days.dropna()
            avg_gap = gaps.mean()
            gap_data.append({
                "Investor ID": inv_id,
                "SIP Transaction Count": len(inv_sip),
                "Average Transaction Gap (Days)": round(avg_gap, 2),
                "Status": "At-Risk (Gap > 35d)" if avg_gap > 35 else "Continuous"
            })
        
        gap_df = pd.DataFrame(gap_data)
        at_risk_df = gap_df[gap_df['Status'] == "At-Risk (Gap > 35d)"]
        
        st.write(f"Total investors analyzed (6+ SIPs): **{len(gap_df)}**")
        st.write(f"Investors flagged as **At-Risk**: **{len(at_risk_df)}** ({len(at_risk_df)/len(gap_df)*100:.1f}%)")
        
        st.dataframe(gap_df.style.applymap(
            lambda val: 'background-color: #fee2e2; color: #991b1b;' if val == "At-Risk (Gap > 35d)" else '',
            subset=['Status']
        ), use_container_width=True)

# ----------------- PAGE 5: ADVANCED ANALYTICS & RECOMMENDER -----------------
elif page == "🔮 Advanced Analytics & Recommender":
    st.title("Advanced Financial Analytics & Portfolio Optimizer")
    st.write("Explore tail risk, run Monte Carlo simulations, compute Markowitz Frontiers, and query the fund recommender.")
    st.write("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🛡️ Tail Risk (VaR / CVaR)",
        "📈 Rolling Sharpe Ratio",
        "🎲 Monte Carlo Simulation",
        "🎯 Efficient Frontier Optimization",
        "🤖 Risk Fund Recommender"
    ])

    # Helper calculations for return series
    if not nav_data.empty:
        nav_pivot = nav_data.pivot(index="calendar_date", columns="scheme_name", values="nav").sort_index()
        returns = nav_pivot.pct_change().dropna(how="all")

    # 1. VaR / CVaR Tail Risk
    with tab1:
        st.subheader("95% Daily Historical Value at Risk (VaR) & Conditional VaR (CVaR)")
        if not nav_data.empty:
            var_rows = []
            for col in returns.columns:
                ret = returns[col].dropna()
                var_95 = np.percentile(ret, 5)
                cvar_95 = ret[ret <= var_95].mean()
                var_rows.append({
                    "Scheme Name": col,
                    "95% Historical VaR": f"{var_95*100:.4f}%",
                    "95% Conditional VaR (CVaR)": f"{cvar_95*100:.4f}%"
                })
            st.dataframe(pd.DataFrame(var_rows), use_container_width=True)

            # Histogram of returns for a selected scheme
            st.write("")
            st.subheader("Daily Returns Distribution Histogram")
            hist_scheme = st.selectbox("Select Scheme for Return Distribution", returns.columns)
            fig_hist = px.histogram(
                returns[hist_scheme].dropna() * 100,
                nbins=100,
                labels={'value': 'Daily Return (%)'},
                title=f"Return Distribution — {hist_scheme.split(' - ')[0]}"
            )
            fig_hist.update_layout(template="plotly_white", showlegend=False)
            st.plotly_chart(fig_hist, use_container_width=True)

    # 2. Rolling Sharpe Ratio
    with tab2:
        st.subheader("Rolling 90-Day Sharpe Ratio Over Time")
        if not nav_data.empty:
            rolling_sharpe_df = pd.DataFrame(index=returns.index)
            RF_daily = 0.065 / 252
            
            for col in returns.columns:
                mean_90 = returns[col].rolling(90).mean()
                std_90 = returns[col].rolling(90).std()
                rolling_sharpe_df[col] = ((mean_90 - RF_daily) / std_90) * np.sqrt(252)
            
            rolling_sharpe_clean = rolling_sharpe_df.dropna(how="all").reset_index()
            # Select funds to display
            selected_funds = st.multiselect("Select Funds to Plot", list(returns.columns), default=list(returns.columns)[:3])
            
            if selected_funds:
                fig_rolling = px.line(
                    rolling_sharpe_clean,
                    x='calendar_date',
                    y=selected_funds,
                    labels={'calendar_date': 'Date', 'value': '90-Day Sharpe Ratio'},
                    title="Rolling Sharpe Ratio Viewer"
                )
                fig_rolling.update_layout(template="plotly_white")
                st.plotly_chart(fig_rolling, use_container_width=True)

    # 3. Monte Carlo Simulation
    with tab3:
        st.subheader("5-Year NAV Growth Projections via Log-Returns Drift")
        mc_scheme = st.selectbox("Select Target Scheme for Projection", list(returns.columns))
        
        if st.button("Run Monte Carlo (1,000 Simulations)"):
            fund_ret = returns[mc_scheme].dropna()
            log_returns = np.log(1 + fund_ret)
            mu = log_returns.mean()
            var = log_returns.var()
            drift = mu - (0.5 * var)
            std_dev = log_returns.std()
            
            n_sim_days = 5 * 252
            n_sims = 1000
            S0 = nav_pivot[mc_scheme].dropna().iloc[-1]
            
            np.random.seed(42)
            daily_sim_returns = np.exp(drift + std_dev * np.random.normal(0, 1, (n_sim_days, n_sims)))
            
            paths = np.zeros_like(daily_sim_returns)
            paths[0] = S0 * daily_sim_returns[0]
            for t in range(1, n_sim_days):
                paths[t] = paths[t-1] * daily_sim_returns[t]
                
            time_index = pd.date_range(start=nav_pivot.index[-1], periods=n_sim_days, freq="B")
            p10 = np.percentile(paths, 10, axis=1)
            p50 = np.percentile(paths, 50, axis=1)
            p90 = np.percentile(paths, 90, axis=1)
            
            # Plot using Plotly Graph Objects
            fig_mc = ob.Figure()
            # Plot some sample paths
            for i in range(15):
                fig_mc.add_trace(ob.Scatter(x=time_index, y=paths[:, i], mode='lines', line=dict(color='rgba(65, 84, 241, 0.1)'), showlegend=False))
                
            fig_mc.add_trace(ob.Scatter(x=time_index, y=p50, mode='lines', name='Median Projection (50th %)', line=dict(color='#0f172a', width=2)))
            fig_mc.add_trace(ob.Scatter(x=time_index, y=p90, mode='lines', line=dict(width=0), showlegend=False))
            fig_mc.add_trace(ob.Scatter(x=time_index, y=p10, mode='lines', fill='tonexty', fillcolor='rgba(65, 84, 241, 0.15)', name='80% Uncertainty Band'))
            
            fig_mc.update_layout(
                title=f"Monte Carlo 5-Year NAV Projection — {mc_scheme.split(' - ')[0]}",
                xaxis_title="Date",
                yaxis_title="Projected NAV (Rebased)",
                template="plotly_white"
            )
            st.plotly_chart(fig_mc, use_container_width=True)

    # 4. Markowitz Efficient Frontier Portfolio Optimization
    with tab4:
        st.subheader("Markowitz Efficient Frontier Simulation & Allocation")
        
        funds_for_frontier = [
            "Nippon India Large Cap Fund - Direct Plan Growth Plan - Growth Option",
            "Axis ELSS Tax Saver Fund - Direct Plan - Growth Option",
            "quant Mid Cap Fund - Growth Option - Direct Plan",
            "SBI Small Cap Fund - Direct Plan - Growth",
            "HDFC Money Market Fund - Growth Option - Direct Plan"
        ]
        
        if st.button("Simulate 5,000 Portfolios"):
            selected_returns = returns[funds_for_frontier].dropna()
            ann_returns = selected_returns.mean() * 252
            cov_matrix = selected_returns.cov() * 252
            
            num_portfolios = 5000
            results = np.zeros((3, num_portfolios))
            weights_record = []
            
            np.random.seed(42)
            for i in range(num_portfolios):
                w_vec = np.random.random(5)
                w_vec /= np.sum(w_vec)
                weights_record.append(w_vec)
                
                portfolio_return = np.sum(w_vec * ann_returns)
                portfolio_std = np.sqrt(np.dot(w_vec.T, np.dot(cov_matrix, w_vec)))
                portfolio_sharpe = (portfolio_return - 0.065) / portfolio_std
                
                results[0, i] = portfolio_return
                results[1, i] = portfolio_std
                results[2, i] = portfolio_sharpe
                
            max_sharpe_idx = np.argmax(results[2])
            sd_msr, ret_msr = results[1, max_sharpe_idx], results[0, max_sharpe_idx]
            weights_msr = weights_record[max_sharpe_idx]
            
            min_vol_idx = np.argmin(results[1])
            sd_mvp, ret_mvp = results[1, min_vol_idx], results[0, min_vol_idx]
            weights_mvp = weights_record[min_vol_idx]
            
            # Scatter plot using Plotly
            fig_ef = px.scatter(
                x=results[1] * 100,
                y=results[0] * 100,
                color=results[2],
                labels={'x': 'Expected Volatility (%)', 'y': 'Expected Return (%)', 'color': 'Sharpe Ratio'},
                color_continuous_scale='viridis'
            )
            # Add markers for MSR and MVP
            fig_ef.add_trace(ob.Scatter(x=[sd_msr*100], y=[ret_msr*100], mode='markers', marker=dict(symbol='star', size=15, color='red'), name='Max Sharpe Portfolio (MSR)'))
            fig_ef.add_trace(ob.Scatter(x=[sd_mvp*100], y=[ret_mvp*100], mode='markers', marker=dict(symbol='star', size=15, color='blue'), name='Min Volatility Portfolio (MVP)'))
            
            fig_ef.update_layout(template="plotly_white", title="Markowitz Efficient Frontier Plot")
            st.plotly_chart(fig_ef, use_container_width=True)
            
            # Show Allocations
            col_msr, col_mvp = st.columns(2)
            with col_msr:
                st.write("**MSR Portfolio Allocation:**")
                msr_dict = {f.split(' - ')[0]: f"{w*100:.2f}%" for f, w in zip(funds_for_frontier, weights_msr)}
                st.json(msr_dict)
            with col_mvp:
                st.write("**MVP Portfolio Allocation:**")
                mvp_dict = {f.split(' - ')[0]: f"{w*100:.2f}%" for f, w in zip(funds_for_frontier, weights_mvp)}
                st.json(mvp_dict)

    # 5. Fund Recommender
    with tab5:
        st.subheader("Risk Appetite-Based Fund Recommender Engine")
        risk_input = st.radio("Select your Risk Appetite level:", ["Low (Debt funds)", "Moderate (Large Cap & ELSS)", "High (Mid Cap & Small Cap)"])
        
        if st.button("Generate Recommendations"):
            risk_app = risk_input.split(" ")[0].strip()
            
            def cat_to_risk(cat):
                cat_lower = cat.lower()
                if "debt" in cat_lower or "money market" in cat_lower:
                    return "Low"
                elif "large cap" in cat_lower or "elss" in cat_lower:
                    return "Moderate"
                else:
                    return "High"
            
            rec_df = perf_data.copy()
            rec_df["risk_grade"] = rec_df["scheme_category"].apply(cat_to_risk)
            matched = rec_df[rec_df["risk_grade"] == risk_app].sort_values("sharpe_ratio", ascending=False)
            
            st.write(f"Top Recommended Funds for **{risk_app.upper()}** risk profile:")
            st.dataframe(matched[['scheme_name', 'scheme_category', 'sharpe_ratio']].rename(columns={
                'scheme_name': 'Scheme Name',
                'scheme_category': 'Category',
                'sharpe_ratio': 'Sharpe Ratio'
            }), use_container_width=True)
