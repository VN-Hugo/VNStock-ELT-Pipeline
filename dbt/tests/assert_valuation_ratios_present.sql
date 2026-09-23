-- Guards against the old bug where P/E and P/B silently came back NULL for every period.
-- Warns instead of failing because loss-making quarters can legitimately have no P/E.
{{ config(severity='warn') }}
SELECT symbol, report_period
FROM {{ ref('silver_financial_statements') }}
WHERE pe_ratio IS NULL OR pb_ratio IS NULL
