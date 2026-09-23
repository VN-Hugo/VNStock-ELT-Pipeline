SELECT symbol, source, report_period, COUNT(*) AS row_count
FROM {{ ref('silver_financial_statements') }}
GROUP BY symbol, source, report_period
HAVING COUNT(*) > 1
