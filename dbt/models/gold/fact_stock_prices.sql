WITH prices AS (
    SELECT
        *,
        LAG(close) OVER w AS previous_close
    FROM {{ ref('silver_stock_prices') }}
    WINDOW w AS (PARTITION BY symbol, source ORDER BY trading_date)
), returns AS (
    SELECT
        *,
        (close - previous_close) / NULLIF(previous_close, 0) AS daily_return
    FROM prices
)

SELECT
    r.symbol,
    r.trading_date,
    r.source,
    r.open,
    r.high,
    r.low,
    r.close,
    r.volume,
    r.close * 1000 * r.volume AS traded_value_vnd,
    r.close - r.previous_close AS price_change,
    r.daily_return,
    AVG(r.close) OVER (PARTITION BY r.symbol, r.source ORDER BY r.trading_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma_20,
    AVG(r.close) OVER (PARTITION BY r.symbol, r.source ORDER BY r.trading_date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) AS ma_50,
    AVG(r.volume) OVER (PARTITION BY r.symbol, r.source ORDER BY r.trading_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS avg_volume_20,
    -- Annualised 20-session volatility (about 250 trading days a year)
    STDDEV_SAMP(r.daily_return) OVER (PARTITION BY r.symbol, r.source ORDER BY r.trading_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) * SQRT(250)::NUMERIC AS volatility_20,
    -- NULL before the pipeline started snapshotting the price board (see silver_foreign_trading)
    f.foreign_buy_vol,
    f.foreign_sell_vol,
    f.foreign_net_vol,
    r.ingestion_date
FROM returns AS r
LEFT JOIN {{ ref('silver_foreign_trading') }} AS f
    ON f.symbol = r.symbol
   AND f.trading_date = r.trading_date
