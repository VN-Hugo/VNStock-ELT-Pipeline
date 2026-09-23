-- Bronze is append-only (every run inserts again), so keep the latest extraction per day.
WITH ranked AS (
    SELECT
        UPPER(TRIM(symbol)) AS symbol,
        CAST(trading_date AS DATE) AS trading_date,
        CAST(open AS NUMERIC) AS open,
        CAST(high AS NUMERIC) AS high,
        CAST(low AS NUMERIC) AS low,
        CAST(close AS NUMERIC) AS close,
        CAST(volume AS NUMERIC) AS volume,
        UPPER(TRIM(source)) AS source,
        CAST(ingestion_date AS DATE) AS ingestion_date,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(symbol)), UPPER(TRIM(source)), CAST(trading_date AS DATE)
            ORDER BY CAST(ingestion_date AS DATE) DESC NULLS LAST, extracted_at DESC NULLS LAST
        ) AS row_number
    FROM {{ source('bronze', 'historical_prices_raw') }}
    WHERE NULLIF(TRIM(symbol), '') IS NOT NULL
      AND NULLIF(TRIM(trading_date), '') IS NOT NULL
)

-- Prices are adjusted for dividends/splits and quoted in thousand VND (65.18 = 65,180 VND).
SELECT
    symbol,
    trading_date,
    open,
    high,
    low,
    close,
    volume,
    source,
    ingestion_date
FROM ranked
WHERE row_number = 1
