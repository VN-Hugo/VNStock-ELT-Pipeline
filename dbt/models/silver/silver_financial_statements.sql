WITH ranked AS (
    SELECT
        UPPER(TRIM(symbol)) AS symbol,
        TRIM(report_period) AS report_period,
        CAST(revenue AS NUMERIC) AS revenue,
        CAST(profit AS NUMERIC) AS profit,
        CAST(profit_parent AS NUMERIC) AS profit_parent,
        CAST(pe_ratio AS NUMERIC) AS pe_ratio,
        CAST(pb_ratio AS NUMERIC) AS pb_ratio,
        CAST(roe AS NUMERIC) AS roe,
        CAST(roa AS NUMERIC) AS roa,
        CAST(net_margin AS NUMERIC) AS net_margin,
        CAST(debt_to_equity AS NUMERIC) AS debt_to_equity,
        CAST(market_cap AS NUMERIC) AS market_cap,
        CAST(shares_outstanding AS NUMERIC) AS shares_outstanding,
        UPPER(TRIM(source)) AS source,
        CAST(ingestion_date AS DATE) AS ingestion_date,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(symbol)), UPPER(TRIM(source)), TRIM(report_period)
            ORDER BY CAST(ingestion_date AS DATE) DESC NULLS LAST, extracted_at DESC NULLS LAST
        ) AS row_number
    FROM {{ source('bronze', 'financial_statements_raw') }}
    WHERE NULLIF(TRIM(symbol), '') IS NOT NULL
      AND NULLIF(TRIM(report_period), '') IS NOT NULL
), typed AS (
    SELECT
        *,
        SPLIT_PART(report_period, '-', 1)::INTEGER AS report_year,
        SPLIT_PART(report_period, '-', 2) AS report_quarter,
        RIGHT(report_period, 1)::INTEGER AS report_quarter_num
    FROM ranked
    WHERE row_number = 1
)

SELECT
    symbol,
    report_period,
    report_year,
    report_quarter,
    report_quarter_num,
    (MAKE_DATE(report_year, report_quarter_num * 3, 1) + INTERVAL '1 month' - INTERVAL '1 day')::DATE AS quarter_end_date,
    -- Reports are published up to 45 days after quarter end. Join financials to prices on
    -- available_date (not quarter_end_date) to avoid look-ahead bias.
    (MAKE_DATE(report_year, report_quarter_num * 3, 1) + INTERVAL '1 month' - INTERVAL '1 day' + INTERVAL '45 days')::DATE AS available_date,
    revenue,
    profit,
    -- Companies without minority interests may not report the split; fall back to total profit
    COALESCE(profit_parent, profit) AS profit_parent,
    pe_ratio,
    pb_ratio,
    roe,
    roa,
    net_margin,
    debt_to_equity,
    market_cap,
    shares_outstanding,
    source,
    ingestion_date
FROM typed
