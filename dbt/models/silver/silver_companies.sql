WITH ranked_companies AS (
    SELECT
        UPPER(TRIM(symbol)) AS symbol,
        NULLIF(TRIM(company_name), '') AS company_name,
        NULLIF(TRIM(exchange), '') AS exchange,
        NULLIF(TRIM(industry), '') AS industry,
        NULLIF(TRIM(company_type), '') AS company_type,
        CAST(NULLIF(TRIM(is_bank), '') AS BOOLEAN) AS is_bank,
        CAST(shares_outstanding AS NUMERIC) AS shares_outstanding,
        CAST(foreign_ownership_pct AS NUMERIC) AS foreign_ownership_pct,
        CAST(foreign_ownership_limit_pct AS NUMERIC) AS foreign_ownership_limit_pct,
        UPPER(TRIM(source)) AS source,
        CAST(ingestion_date AS DATE) AS ingestion_date,
        ROW_NUMBER() OVER (
            PARTITION BY UPPER(TRIM(symbol)), UPPER(TRIM(source))
            ORDER BY CAST(ingestion_date AS DATE) DESC NULLS LAST, extracted_at DESC NULLS LAST
        ) AS row_number
    FROM {{ source('bronze', 'companies_raw') }}
    WHERE NULLIF(TRIM(symbol), '') IS NOT NULL
)

SELECT
    symbol,
    company_name,
    exchange,
    industry,
    company_type,
    COALESCE(is_bank, company_type = 'NH', FALSE) AS is_bank,
    shares_outstanding,
    foreign_ownership_pct,
    foreign_ownership_limit_pct,
    foreign_ownership_limit_pct - foreign_ownership_pct AS foreign_room_pct,
    source,
    ingestion_date
FROM ranked_companies
WHERE row_number = 1
