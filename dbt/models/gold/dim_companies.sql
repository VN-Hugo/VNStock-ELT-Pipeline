SELECT
    symbol,
    company_name,
    exchange,
    industry,
    company_type,
    is_bank,
    shares_outstanding,
    foreign_ownership_pct,
    foreign_ownership_limit_pct,
    foreign_room_pct,
    source,
    ingestion_date
FROM {{ ref('silver_companies') }}
