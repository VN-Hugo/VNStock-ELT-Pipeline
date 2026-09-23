WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY symbol, source ORDER BY trading_date DESC) AS recency
    FROM {{ ref('fact_stock_prices') }}
)

SELECT
    symbol,
    source,
    MAX(trading_date) AS latest_trading_date,
    MAX(close) FILTER (WHERE recency = 1) AS latest_close,
    MAX(ma_20) FILTER (WHERE recency = 1) AS latest_ma_20,
    MAX(volatility_20) FILTER (WHERE recency = 1) AS latest_volatility_20,
    AVG(close) AS average_close,
    SUM(volume) AS total_volume,
    SUM(traded_value_vnd) AS total_traded_value_vnd,
    AVG(daily_return) AS average_daily_return,
    SUM(foreign_buy_vol) AS total_foreign_buy_vol,
    SUM(foreign_sell_vol) AS total_foreign_sell_vol,
    SUM(foreign_net_vol) AS total_foreign_net_vol,
    COUNT(foreign_net_vol) AS days_with_foreign_data
FROM ranked
GROUP BY symbol, source
