-- Gold: one row per Community Area for the zoom-10 to 12 map layer.
-- Mirrors supabase/migrations/006_gold_materialized_views.sql (gold_cca_summary).
{{ config(materialized='table') }}

SELECT
  c.id,
  c.name,
  c.geometry,
  c.rent_median,
  c.safety_score,
  c.walk_score,
  c.disp_score,

  COUNT(DISTINCT b.pin)                                      AS building_count,
  COALESCE(AVG(b.landlord_score), 0)::NUMERIC(4,2)           AS avg_landlord_score,
  COUNT(DISTINCT b.pin) FILTER (WHERE b.tax_current = FALSE) AS delinquent_buildings,

  (SELECT COUNT(*) FILTER (WHERE ci.type = 'violent')::INT
     FROM {{ source('silver', 'cpd_incidents') }} ci
     WHERE ST_Contains(c.geometry, ci.location)
       AND ci.date >= NOW() - INTERVAL '1 year')             AS violent_1yr,

  NOW() AS refreshed_at

FROM {{ source('silver', 'ccas') }} c
LEFT JOIN {{ source('silver', 'buildings') }} b
  ON ST_Contains(c.geometry, b.location)
GROUP BY c.id, c.name, c.geometry, c.rent_median,
         c.safety_score, c.walk_score, c.disp_score
