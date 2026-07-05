# Mutual Fund Analytics Capstone Project

An end-to-end data analytics and quantitative finance capstone project built on historical NAV data, demographic details, and mock systematic transaction logs. The project implements a robust ETL pipeline, database dimensional modeling, performance scorecarding, risk analytics, and portfolio optimization.

---

## 📁 Repository Structure

The project has been structured according to the Capstone guidelines:

```text
bluestock_mf_capstone/
├── data/
│   ├── raw/                 ← Original downloaded NAV and investor transaction CSVs
│   ├── processed/           ← Cleaned, merged, and dimension-modeled CSVs
│   └── db/                  ← SQLite database (bluestock_mf.db)
├── notebooks/
│   ├── 01_data_ingestion.ipynb
│   ├── 02_data_cleaning.ipynb
│   ├── 03_eda_analysis.ipynb
│   ├── 04_performance_analytics.ipynb
│   └── 05_advanced_analytics.ipynb
├── scripts/
│   ├── data_ingestion.py    ← Script to fetch NAV data from API
│   ├── etl_pipeline.py      ← Master script cleaning data and loading SQLite star schema
│   ├── compute_metrics.py   ← Calculates risk/return statistics & updates fact_performance
│   ├── live_nav_fetch.py    ← CLI script to fetch today's latest NAV from mfapi.in
│   └── recommender.py       ← Risk-profile matching and recommendation engine
├── sql/
│   ├── schema.sql           ← SQLite star schema table definitions
│   └── queries.sql          ← Multi-table queries verifying counts and reporting AUM
├── reports/                 ← CSV scorecards, analysis charts, and PDF reports
├── dashboard/               ← Tableau or PowerBI interactive dashboard assets
├── requirements.txt         ← Project package dependencies
└── README.md                ← Project documentation
```

---

## 🛠️ Installation & Setup

1. **Virtual Environment Setup**:
   Create a virtual environment and activate it:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate       # On Windows
   source .venv/bin/activate    # On macOS/Linux
   ```

2. **Install Dependencies**:
   Install all quantitative, visualization, and database packages:
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify Database Setup**:
   Check if the database resides in `data/db/bluestock_mf.db` with proper tables.

---

## 🚀 Execution Guide

### 1. Data Cleaning & Database Load
Run the master ETL pipeline to clean raw data, generate date dimensions, and populate the star-schema database in SQLite:
```bash
python scripts/etl_pipeline.py
```

### 2. Compute Performance Metrics
Compute CAGRs (1y, 3y, 5y) using trading days (252 per year) instead of calendar days to avoid errors, and write annualized volatility and Sharpe ratios directly to the `fact_performance` database table:
```bash
python scripts/compute_metrics.py
```

### 3. Mutual Fund Recommender (CLI Tool)
Run the recommender script either in CLI mode or interactively:
- **CLI Mode**: Recommend top 3 funds for high risk appetite:
  ```bash
  python scripts/recommender.py --risk High
  ```
- **Interactive Mode**: Select risk appetites dynamically:
  ```bash
  python scripts/recommender.py
  ```

### 4. Fetch Live NAV
Fetch current day NAV directly from the `mfapi.in` API for any AMFI scheme code (e.g. Nippon India Large Cap `118632`):
```bash
python scripts/live_nav_fetch.py --code 118632
```

---

## 📊 Analytical Insights & Findings

### 1. Daily Tail Risk: Value at Risk (VaR) & CVaR (95%)
Daily Value at Risk (VaR) and Conditional Value at Risk (CVaR) were calculated dynamically at a 95% confidence level:
* **Nippon India Large Cap Fund** shows the highest tail risk with a **95% daily VaR of -1.6702%** and a **95% daily CVaR of -2.3873%**.
* **HDFC Money Market Fund** shows near-zero daily tail risk (**95% VaR of -0.0076%** and **95% CVaR of -0.0213%**), highlighting its capital preservation strengths.

### 2. Risk-Adjusted Returns (Sharpe Ratios)
Annualized Sharpe ratios (using a 6.5% risk-free rate proxy) show high performance in high-risk categories:
* **SBI Small Cap Fund**: **1.0395** (Strongest risk-adjusted performance)
* **quant Mid Cap Fund**: **0.6223** (Highest CAGR at +17.92%)
* **Aditya Birla Sun Life Banking & PSU Debt**: **-0.7227** (Underperformed with -7.08% 5y CAGR)

### 3. Sector Concentration (HHI)
Using the Herfindahl-Hirschman Index ($\sum w_i^2$) across equity funds:
* **Nippon India Large Cap**: HHI = **1900** (Sector concentrated due to heavy Financial Services weight)
* **SBI Small Cap**: HHI = **1406** (Highly diversified across Consumer Durables, Industrials, and Health)

### 4. Behavioral SIP Gaps
* **100% of investors** with 6+ SIP transactions are flagged as **at-risk** due to an average gap between consecutive investments exceeding 35 days (typical gaps range from 80 to 130 days), highlighting significant inconsistency in monthly systematic investing.

---

## 🏆 Bonus Capstone Challenges

* **B3: Monte Carlo Simulation (5-Year Projection)**: Run inside `05_advanced_analytics.ipynb` to project the NAV growth of SBI Small Cap Fund over 5 years (1,260 trading days) using log-return drift and standard deviation, showing the median path and 80% uncertainty bands.
* **B4: Markowitz Efficient Frontier**: Simulates 5,000 random weight allocations across 5 key funds, plotting the frontier curve and identifying the Minimum Variance Portfolio (MVP) and Maximum Sharpe Ratio (MSR) allocations.
