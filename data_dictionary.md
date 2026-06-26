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
