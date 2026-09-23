-- One wide row per symbol and trading day for BI tools (Power BI, Streamlit):
-- prices + technical features + company attributes + the latest financials that were
-- already public on that day (point-in-time join on available_date, no look-ahead bias).
WITH prices AS (
    SELECT * FROM {{ ref('fact_stock_prices') }}
), companies AS (
    SELECT * FROM {{ ref('dim_companies') }}
), financials AS (
    SELECT
        symbol,
        report_period,
        available_date,
        roe,
        net_margin,
        revenue_growth_yoy,
        profit_growth_yoy,
        -- Back out the source's own TTM earnings and book value so daily P/E and P/B
        -- match the definitions behind pe_ratio / pb_ratio.
        market_cap / NULLIF(pe_ratio, 0) AS earnings_ttm,
        market_cap / NULLIF(pb_ratio, 0) AS book_value
    FROM {{ ref('fact_financial_statements') }}
)

SELECT
    p.symbol,
    p.trading_date,
    c.company_name,
    c.exchange,
    c.industry,
    c.is_bank,
    p.open,
    p.high,
    p.low,
    p.close,
    p.volume,
    p.traded_value_vnd,
    p.daily_return,
    p.ma_20,
    p.ma_50,
    p.avg_volume_20,
    p.volatility_20,
    p.foreign_buy_vol,
    p.foreign_sell_vol,
    p.foreign_net_vol,
    -- Adjusted price x current share count ~ market cap in today's share terms
    p.close * 1000 * c.shares_outstanding AS market_cap_vnd,
    f.report_period AS latest_report_period,
    (p.close * 1000 * c.shares_outstanding) / NULLIF(f.earnings_ttm, 0) AS pe_daily,
    (p.close * 1000 * c.shares_outstanding) / NULLIF(f.book_value, 0) AS pb_daily,
    f.roe,
    f.net_margin,
    f.revenue_growth_yoy,
    f.profit_growth_yoy
FROM prices AS p
LEFT JOIN companies AS c
    ON c.symbol = p.symbol
LEFT JOIN LATERAL (
    SELECT *
    FROM financials AS fin
    WHERE fin.symbol = p.symbol
      AND fin.available_date <= p.trading_date
    ORDER BY fin.available_date DESC
    LIMIT 1
) AS f ON TRUE
