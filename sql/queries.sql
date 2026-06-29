SELECT f.scheme_name, f.fund_house, a.aum_value, a.observation_count, a.proxy_method
FROM fact_aum a
JOIN dim_fund f ON f.fund_key = a.fund_key
ORDER BY a.aum_value DESC
LIMIT 5;

SELECT d.year, d.month, d.month_name, ROUND(AVG(n.nav), 4) AS average_nav
FROM fact_nav n
JOIN dim_date d ON d.date_key = n.date_key
GROUP BY d.year, d.month, d.month_name
ORDER BY d.year, d.month;

WITH sip_by_year AS (
    SELECT d.year, SUM(t.amount) AS sip_amount
    FROM fact_transactions t
    JOIN dim_date d ON d.date_key = t.transaction_date_key
    WHERE t.transaction_type = 'SIP'
    GROUP BY d.year
)
SELECT
    year,
    sip_amount,
    ROUND(
        100.0 * (sip_amount - LAG(sip_amount) OVER (ORDER BY year))
        / NULLIF(LAG(sip_amount) OVER (ORDER BY year), 0),
        2
    ) AS yoy_growth_pct
FROM sip_by_year
ORDER BY year;

SELECT COALESCE(state, 'Unknown') AS state, COUNT(*) AS transaction_count, ROUND(SUM(amount), 2) AS total_amount
FROM fact_transactions
GROUP BY COALESCE(state, 'Unknown')
ORDER BY transaction_count DESC, total_amount DESC;

SELECT f.scheme_name, f.fund_house, p.expense_ratio
FROM fact_performance p
JOIN dim_fund f ON f.fund_key = p.fund_key
WHERE p.expense_ratio < 1.0
ORDER BY p.expense_ratio ASC;

SELECT f.scheme_name, d.calendar_date, n.nav, n.previous_nav, (n.nav - n.previous_nav) AS nav_change
FROM fact_nav n
JOIN dim_fund f ON f.fund_key = n.fund_key
JOIN dim_date d ON d.date_key = n.date_key
WHERE n.previous_nav IS NOT NULL
ORDER BY ABS(n.nav - n.previous_nav) DESC
LIMIT 10;

SELECT f.fund_house, d.year, d.month, ROUND(AVG(n.nav), 4) AS average_nav
FROM fact_nav n
JOIN dim_fund f ON f.fund_key = n.fund_key
JOIN dim_date d ON d.date_key = n.date_key
GROUP BY f.fund_house, d.year, d.month
ORDER BY f.fund_house, d.year, d.month;

SELECT f.scheme_name, f.fund_house, COUNT(*) AS nav_observations, MIN(d.calendar_date) AS first_observation, MAX(d.calendar_date) AS latest_observation
FROM fact_nav n
JOIN dim_fund f ON f.fund_key = n.fund_key
JOIN dim_date d ON d.date_key = n.date_key
GROUP BY f.scheme_name, f.fund_house
ORDER BY nav_observations DESC
LIMIT 10;

SELECT f.scheme_name, COUNT(*) AS anomaly_rows
FROM fact_performance p
JOIN dim_fund f ON f.fund_key = p.fund_key
WHERE p.anomaly_flag = 1
GROUP BY f.scheme_name
ORDER BY anomaly_rows DESC, f.scheme_name;

SELECT f.scheme_name, d.calendar_date, n.nav
FROM fact_nav n
JOIN dim_fund f ON f.fund_key = n.fund_key
JOIN dim_date d ON d.date_key = n.date_key
WHERE d.is_month_end = 1
ORDER BY f.scheme_name, d.calendar_date;
