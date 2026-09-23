-- Fails on impossible candles: high below low/open/close, or negative prices or volume.
SELECT *
FROM {{ ref('silver_stock_prices') }}
WHERE high < low
   OR high < GREATEST(open, close)
   OR low > LEAST(open, close)
   OR low <= 0
   OR volume < 0
