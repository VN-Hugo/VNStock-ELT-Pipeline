WITH financials AS (
    SELECT
        *,
        LAG(revenue, 4) OVER w AS revenue_same_quarter_last_year,
        LAG(profit_parent, 4) OVER w AS profit_parent_same_quarter_last_year,
        SUM(profit_parent) OVER (w ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS profit_parent_ttm,
        COUNT(profit_parent) OVER (w ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) AS quarters_in_ttm
    FROM {{ ref('silver_financial_statements') }}
    WINDOW w AS (PARTITION BY symbol, source ORDER BY report_year, report_quarter_num)
)

SELECT
    f.symbol,
    f.report_period,
    f.report_year,
    f.report_quarter,
    f.quarter_end_date,
    f.public_date,
    f.available_date,
    f.source,
    c.is_bank,
    f.revenue,
    f.profit,
    f.profit_parent,
    f.profit / NULLIF(f.revenue, 0) AS profit_margin,
    (f.revenue - f.revenue_same_quarter_last_year) / NULLIF(ABS(f.revenue_same_quarter_last_year), 0) AS revenue_growth_yoy,
    -- Growth and TTM use profit attributable to the parent company (the EPS/P-E basis)
    (f.profit_parent - f.profit_parent_same_quarter_last_year) / NULLIF(ABS(f.profit_parent_same_quarter_last_year), 0) AS profit_growth_yoy,
    CASE WHEN f.quarters_in_ttm = 4 THEN f.profit_parent_ttm END AS profit_ttm,
    f.pe_ratio,
    f.pb_ratio,
    f.roe,
    f.roa,
    f.net_margin,
    f.debt_to_equity,
    f.market_cap,
    f.shares_outstanding,
    f.nim,
    f.npl,
    f.casa_ratio,
    f.ingestion_date
FROM financials AS f
LEFT JOIN {{ ref('silver_companies') }} AS c
    ON c.symbol = f.symbol
