"""All analytics SQL for the platform, in one reviewable place.

Conventions:
- Latest year is resolved dynamically (works for synthetic or real data).
- Deciling uses NTILE(10) over total claims: decile 10 = highest volume.
"""

LATEST_YEAR = "SELECT MAX(year) FROM fact_prescriptions"

TERRITORY_KPIS = """
WITH latest AS (SELECT MAX(year) AS y FROM fact_prescriptions),
prev AS (SELECT MAX(year) - 1 AS y FROM fact_prescriptions)
SELECT
    t.territory_id,
    t.territory_name,
    t.state,
    t.region,
    t.rep_name,
    COUNT(DISTINCT p.npi)                                   AS prescribers,
    COALESCE(SUM(CASE WHEN f.year = (SELECT y FROM latest)
                      THEN f.total_claims END), 0)          AS claims,
    COALESCE(SUM(CASE WHEN f.year = (SELECT y FROM latest)
                      THEN f.total_drug_cost END), 0)       AS drug_cost,
    COALESCE(SUM(CASE WHEN f.year = (SELECT y FROM prev)
                      THEN f.total_claims END), 0)          AS claims_prev,
    RANK() OVER (ORDER BY SUM(CASE WHEN f.year = (SELECT y FROM latest)
                                   THEN f.total_claims END) DESC) AS claims_rank
FROM dim_territory t
JOIN dim_prescriber p ON p.territory_id = t.territory_id
LEFT JOIN fact_prescriptions f ON f.npi = p.npi
GROUP BY t.territory_id
ORDER BY claims DESC
"""

TERRITORY_DETAIL = """
SELECT t.*, COUNT(DISTINCT p.npi) AS prescribers
FROM dim_territory t
JOIN dim_prescriber p ON p.territory_id = t.territory_id
WHERE t.territory_id = ?
GROUP BY t.territory_id
"""

TERRITORY_TREND = """
SELECT f.year,
       SUM(f.total_claims)    AS claims,
       SUM(f.total_drug_cost) AS drug_cost
FROM fact_prescriptions f
JOIN dim_prescriber p ON p.npi = f.npi
WHERE p.territory_id = ?
GROUP BY f.year
ORDER BY f.year
"""

TERRITORY_TOP_DRUGS = """
WITH latest AS (SELECT MAX(year) AS y FROM fact_prescriptions)
SELECT d.brand_name, d.drug_class,
       SUM(f.total_claims)    AS claims,
       SUM(f.total_drug_cost) AS drug_cost
FROM fact_prescriptions f
JOIN dim_prescriber p ON p.npi = f.npi
JOIN dim_drug d       ON d.drug_id = f.drug_id
WHERE p.territory_id = ? AND f.year = (SELECT y FROM latest)
GROUP BY d.drug_id
ORDER BY claims DESC
LIMIT ?
"""

# National deciling: every prescriber ranked by latest-year claims,
# NTILE(10) -> decile 10 = top ~10% by volume.
PRESCRIBER_DECILES = """
WITH latest AS (SELECT MAX(year) AS y FROM fact_prescriptions),
vol AS (
    SELECT p.npi,
           p.prescriber_name,
           p.specialty,
           p.city,
           p.state,
           p.territory_id,
           SUM(f.total_claims)    AS claims,
           SUM(f.total_drug_cost) AS drug_cost
    FROM dim_prescriber p
    JOIN fact_prescriptions f
      ON f.npi = p.npi AND f.year = (SELECT y FROM latest)
    GROUP BY p.npi
)
SELECT vol.*,
       NTILE(10) OVER (ORDER BY claims) AS decile
FROM vol
"""

PRESCRIBER_PROFILE = """
SELECT p.npi, p.prescriber_name, p.specialty, p.city, p.state,
       t.territory_id, t.territory_name, t.rep_name
FROM dim_prescriber p
JOIN dim_territory t ON t.territory_id = p.territory_id
WHERE p.npi = ?
"""

PRESCRIBER_DRUG_MIX = """
SELECT d.brand_name, d.generic_name, d.drug_class, f.year,
       f.total_claims, f.total_drug_cost, f.total_beneficiaries
FROM fact_prescriptions f
JOIN dim_drug d ON d.drug_id = f.drug_id
WHERE f.npi = ?
ORDER BY f.year DESC, f.total_claims DESC
"""

DRUG_LIST = """
WITH latest AS (SELECT MAX(year) AS y FROM fact_prescriptions)
SELECT d.drug_id, d.brand_name, d.generic_name, d.drug_class,
       COALESCE(SUM(f.total_claims), 0)    AS claims,
       COALESCE(SUM(f.total_drug_cost), 0) AS drug_cost
FROM dim_drug d
LEFT JOIN fact_prescriptions f
       ON f.drug_id = d.drug_id AND f.year = (SELECT y FROM latest)
GROUP BY d.drug_id
ORDER BY claims DESC
"""

DRUG_MARKET = """
WITH latest AS (SELECT MAX(year) AS y FROM fact_prescriptions),
per_territory AS (
    SELECT t.territory_id, t.territory_name, t.state,
           SUM(CASE WHEN f.drug_id = ? THEN f.total_claims ELSE 0 END) AS drug_claims,
           SUM(CASE WHEN d.drug_class = (SELECT drug_class FROM dim_drug WHERE drug_id = ?)
                    THEN f.total_claims ELSE 0 END)                    AS class_claims
    FROM dim_territory t
    JOIN dim_prescriber p ON p.territory_id = t.territory_id
    JOIN fact_prescriptions f ON f.npi = p.npi AND f.year = (SELECT y FROM latest)
    JOIN dim_drug d ON d.drug_id = f.drug_id
    GROUP BY t.territory_id
)
SELECT *,
       ROUND(100.0 * drug_claims / NULLIF(class_claims, 0), 1) AS class_share_pct
FROM per_territory
ORDER BY drug_claims DESC
"""

DRUG_TREND = """
SELECT year, SUM(total_claims) AS claims, SUM(total_drug_cost) AS drug_cost
FROM fact_prescriptions
WHERE drug_id = ?
GROUP BY year ORDER BY year
"""

CALL_PLAN_BASE = """
WITH latest AS (SELECT MAX(year) AS y FROM fact_prescriptions),
vol AS (
    SELECT p.npi, p.territory_id, SUM(f.total_claims) AS claims
    FROM dim_prescriber p
    JOIN fact_prescriptions f
      ON f.npi = p.npi AND f.year = (SELECT y FROM latest)
    GROUP BY p.npi
),
dec AS (
    SELECT npi, territory_id, claims,
           NTILE(10) OVER (ORDER BY claims) AS decile
    FROM vol
)
SELECT territory_id, decile, COUNT(*) AS prescribers, SUM(claims) AS claims
FROM dec
WHERE territory_id = ?
GROUP BY decile
ORDER BY decile DESC
"""
