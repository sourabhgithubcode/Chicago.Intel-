-- Gold: one row per census tract for the zoom-12 to 14 map layer.
-- Mirrors supabase/migrations/006_gold_materialized_views.sql (gold_tract_summary).
{{ config(materialized='table') }}

SELECT
  t.id,
  t.cca_id,
  t.name,
  t.geometry,
  t.rent_median,
  t.rent_moe,
  t.safety_score,
  t.walk_score,
  t.population,
  t.disp_score,

  COUNT(DISTINCT b.pin)                            AS building_count,
  COALESCE(AVG(b.landlord_score), 0)::NUMERIC(4,2) AS avg_landlord_score,

  NOW() AS refreshed_at

FROM {{ source('silver', 'tracts') }} t
LEFT JOIN {{ source('silver', 'buildings') }} b
  ON ST_Contains(t.geometry, b.location)
GROUP BY t.id, t.cca_id, t.name, t.geometry, t.rent_median, t.rent_moe,
         t.safety_score, t.walk_score, t.population, t.disp_score
