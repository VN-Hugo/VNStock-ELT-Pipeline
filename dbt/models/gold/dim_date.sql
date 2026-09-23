WITH trading_days AS (
    SELECT DISTINCT trading_date
    FROM {{ ref('silver_stock_prices') }}
), date_bounds AS (
    SELECT
        MIN(trading_date) AS min_date,
        MAX(trading_date) AS max_date
    FROM {{ ref('silver_stock_prices') }}
)

SELECT
    date_day::DATE AS date_key,
    EXTRACT(YEAR FROM date_day)::INTEGER AS year,
    EXTRACT(QUARTER FROM date_day)::INTEGER AS quarter,
    'Q' || EXTRACT(QUARTER FROM date_day)::INTEGER AS quarter_name,
    EXTRACT(MONTH FROM date_day)::INTEGER AS month,
    TO_CHAR(date_day, 'YYYY-MM') AS year_month,
    EXTRACT(DAY FROM date_day)::INTEGER AS day,
    EXTRACT(ISODOW FROM date_day)::INTEGER AS day_of_week,
    TO_CHAR(date_day, 'Day') AS day_name,
    EXTRACT(ISODOW FROM date_day) IN (6, 7) AS is_weekend,
    -- A weekday without any price bar is a public holiday
    t.trading_date IS NOT NULL AS is_trading_day
FROM date_bounds
CROSS JOIN LATERAL GENERATE_SERIES(min_date, max_date, INTERVAL '1 day') AS date_series(date_day)
LEFT JOIN trading_days AS t
    ON t.trading_date = date_series.date_day::DATE
WHERE min_date IS NOT NULL