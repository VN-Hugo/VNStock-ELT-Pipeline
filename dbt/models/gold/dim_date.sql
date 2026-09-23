WITH date_bounds AS (
    SELECT
        MIN(trading_date) AS min_date,
        MAX(trading_date) AS max_date
    FROM {{ ref('silver_stock_prices') }}
)

SELECT
    date_day AS date_key,
    EXTRACT(YEAR FROM date_day)::INTEGER AS year,
    EXTRACT(QUARTER FROM date_day)::INTEGER AS quarter,
    'Q' || EXTRACT(QUARTER FROM date_day)::INTEGER AS quarter_name,
    EXTRACT(MONTH FROM date_day)::INTEGER AS month,
    TO_CHAR(date_day, 'YYYY-MM') AS year_month,
    EXTRACT(DAY FROM date_day)::INTEGER AS day,
    EXTRACT(ISODOW FROM date_day)::INTEGER AS day_of_week,
    TO_CHAR(date_day, 'Day') AS day_name,
    EXTRACT(ISODOW FROM date_day) IN (6, 7) AS is_weekend
FROM date_bounds,
LATERAL GENERATE_SERIES(min_date, max_date, INTERVAL '1 day') AS date_series(date_day)
WHERE min_date IS NOT NULL