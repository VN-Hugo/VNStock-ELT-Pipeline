-- Fails if Silver still has duplicate rows for the same symbol and day.
SELECT symbol, source, trading_date, COUNT(*) AS row_count
FROM {{ ref('silver_stock_prices') }}
GROUP BY symbol, source, trading_date
HAVING COUNT(*) > 1
