# Mutual Fund Data Dictionary

## Source Files
- `data/raw/nav_*.csv`: NAV history extracts per scheme.
- `data/raw/nav_*.json`: scheme metadata and NAV history payloads.
- `reports/nav_fetch_summary.csv`: high-level NAV summary used for proxy AUM aggregation.

## nav_history_clean.csv
| Column | Type | Business Definition | Source |
| --- | --- | --- | --- |
| amfi_code | INTEGER | Unique AMFI scheme identifier. | Raw CSV / JSON metadata |
| date | DATE | NAV observation date. | Raw NAV CSV and JSON payload |
| nav | REAL | Daily net asset value. | Raw NAV CSV / JSON payload |
| scheme_name | TEXT | Human-readable fund name. | Raw CSV / JSON meta |
| fund_house | TEXT | Asset management company name. | Raw CSV / JSON meta |
| scheme_type | TEXT | Scheme family. | Raw JSON meta |
| scheme_category | TEXT | Fund category. | Raw JSON meta |
| isin_growth | TEXT | Growth option ISIN. | Raw JSON meta |
| isin_div_reinvestment | TEXT | Dividend/reinvestment option ISIN. | Raw JSON meta |
| source_file | TEXT | Originating raw file name. | File system |
| previous_nav | REAL | Previous NAV for the same fund. | Derived |
| nav_change | REAL | Day-over-day NAV change. | Derived |
| nav_return_pct | REAL | Day-over-day NAV return percentage. | Derived |

## dim_fund
| Column | Type | Business Definition | Source |
| --- | --- | --- | --- |
| fund_key | INTEGER | Surrogate primary key. | Derived |
| amfi_code | INTEGER | Natural fund key. | Cleaned NAV history |
| scheme_name | TEXT | Fund name. | Cleaned NAV history |
| fund_house | TEXT | AMC name. | Cleaned NAV history |
| scheme_type | TEXT | Scheme family. | Raw JSON meta |
| scheme_category | TEXT | Fund category. | Raw JSON meta |
| isin_growth | TEXT | Growth ISIN. | Raw JSON meta |
| isin_div_reinvestment | TEXT | Dividend/reinvestment ISIN. | Raw JSON meta |
| source_file | TEXT | Source file. | Cleaned NAV history |
| created_at | TEXT | Row creation timestamp. | SQLite default |

## dim_date
| Column | Type | Business Definition | Source |
| --- | --- | --- | --- |
| date_key | INTEGER | YYYYMMDD surrogate key. | Derived |
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
| source_file | TEXT | Raw file that contributed the row. | Cleaned NAV history |

## fact_aum
| Column | Type | Business Definition | Source |
| --- | --- | --- | --- |
| aum_key | INTEGER | Surrogate fact key. | Derived |
| fund_key | INTEGER | Links to dim_fund. | Cleaned NAV history |
| date_key | INTEGER | Latest observation date for the fund. | Cleaned NAV history |
| aum_value | REAL | NAV-derived AUM proxy because no raw AUM feed is present. | Derived |
| observation_count | INTEGER | Number of NAV observations used. | Derived |
| min_nav | REAL | Minimum observed NAV. | Derived |
| max_nav | REAL | Maximum observed NAV. | Derived |
| proxy_method | TEXT | Method used to approximate AUM. | Derived |
| source_file | TEXT | Originating summary file. | Derived |

## fact_transactions
| Column | Type | Business Definition | Source |
| --- | --- | --- | --- |
| transaction_key | INTEGER | Surrogate transaction key. | Derived |
| fund_key | INTEGER | Links to dim_fund. | Synthetic activity feed |
| transaction_date_key | INTEGER | Links to dim_date. | Synthetic activity feed |
| investor_id | TEXT | Investor identifier. | Synthetic activity feed |
| transaction_type | TEXT | SIP or LUMPSUM transaction type. | Synthetic activity feed |
| amount | REAL | Transaction amount. | Synthetic activity feed |
| units | REAL | Units transacted. | Synthetic activity feed |
| nav | REAL | NAV at transaction time. | Synthetic activity feed |
| state | TEXT | Investor state. | Synthetic activity feed |
| kyc_status | TEXT | KYC status. | Synthetic activity feed |
| source_file | TEXT | Synthetic source label. | Synthetic activity feed |

## dim_investor
| Column | Type | Business Definition | Source |
| --- | --- | --- | --- |
| investor_id | TEXT | Investor identifier. | Synthetic activity feed |
| age_group | TEXT | Investor age band. | Synthetic activity feed |
| gender | TEXT | Investor gender. | Synthetic activity feed |
| state | TEXT | Home state. | Synthetic activity feed |
| city_tier | TEXT | T30/B30 tier flag. | Synthetic activity feed |
| registration_date | TEXT | First onboarding date. | Synthetic activity feed |
| sip_amount | REAL | Typical SIP amount. | Synthetic activity feed |
| source_file | TEXT | Synthetic source label. | Synthetic activity feed |

## fact_performance
Reserved for scheme performance sources when available.
