-- Several runs on the same day -> keep the last snapshot (the most complete session).
WITH ranked AS (
    SELECT
        UPPER(TRIM(symbol)) AS symbol,
        CAST(trading_date AS DATE) AS trading_date,
        CAST(snapshot_at AS TIMESTAMPTZ) AS snapshot_at,
        CAST(foreign_buy_vol AS NUMERIC) AS foreign_buy_vol,
        CAST(foreign_sell_vol AS NUMERIC) AS foreign_sell_vol,
        CAST(foreign_room AS NUMERIC) AS foreign_room,
        UPPER(TRIM(source)) AS source,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(symbol)), CAST(trading_date AS DATE)
            ORDER BY CAST(snapshot_at AS TIMESTAMPTZ) DESC NULLS LAST
        ) AS row_number
    FROM {{ source('bronze', 'foreign_trading_raw') }}
    WHERE NULLIF(TRIM(symbol), '') IS NOT NULL
      AND NULLIF(TRIM(trading_date), '') IS NOT NULL
)

SELECT
    symbol,
    trading_date,
    snapshot_at,
    foreign_buy_vol,
    foreign_sell_vol,
    foreign_buy_vol - foreign_sell_vol AS foreign_net_vol,
    foreign_room,
    source
FROM ranked
WHERE row_number = 1
