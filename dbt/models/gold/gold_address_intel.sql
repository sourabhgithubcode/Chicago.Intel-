-- Gold: one row per building with CCA, tract, nearest CTA, nearest park,
-- and pre-computed 0.25mi (402m) safety aggregates pre-joined.
-- Mirrors supabase/migrations/006_gold_materialized_views.sql (gold_address_intel).
{{ config(materialized='table') }}

SELECT
  b.pin,
  b.address,
  b.address_norm,
  b.location,
  b.owner,
  b.year_built,
  b.purchase_year,
  b.purchase_price,
  b.tax_current,
  b.tax_annual,
  b.violations_5yr,
  b.heat_complaints,
  b.bug_reports,
  b.landlord_score,
  b.flood_zone,
  b.school_elem,

  -- CCA containment
  cca.id            AS cca_id,
  cca.name          AS cca_name,
  cca.rent_median   AS cca_rent_median,
  cca.safety_score  AS cca_safety_score,
  cca.walk_score    AS cca_walk_score,
  cca.disp_score    AS cca_disp_score,

  -- Tract containment
  t.id              AS tract_id,
  t.rent_median     AS tract_rent_median,
  t.rent_moe        AS tract_rent_moe,
  t.disp_score      AS tract_disp_score,

  -- Nearest CTA stop (lateral join, uses GIST index)
  cta.name          AS nearest_cta_name,
  cta.lines         AS nearest_cta_lines,
  cta.distance_m    AS nearest_cta_m,

  -- Nearest park
  p.name            AS nearest_park_name,
  p.acreage         AS nearest_park_acreage,
  p.distance_m      AS nearest_park_m,

  -- Pre-computed 0.25mi safety aggregates
  (SELECT COUNT(*) FILTER (WHERE type = 'violent')::INT
     FROM {{ source('silver', 'cpd_incidents') }}
     WHERE ST_DWithin(location, b.location::geography, 402)
       AND date >= NOW() - INTERVAL '5 years')          AS violent_5yr,
  (SELECT COUNT(*) FILTER (WHERE type = 'property')::INT
     FROM {{ source('silver', 'cpd_incidents') }}
     WHERE ST_DWithin(location, b.location::geography, 402)
       AND date >= NOW() - INTERVAL '5 years')          AS property_5yr,

  NOW() AS refreshed_at

FROM {{ source('silver', 'buildings') }} b
LEFT JOIN {{ source('silver', 'ccas') }} cca
  ON ST_Contains(cca.geometry, b.location)
LEFT JOIN {{ source('silver', 'tracts') }} t
  ON ST_Contains(t.geometry, b.location)
LEFT JOIN LATERAL (
  SELECT name, lines,
         ST_Distance(location, b.location::geography)::INT AS distance_m
  FROM {{ source('silver', 'cta_stops') }}
  ORDER BY location <-> b.location::geography
  LIMIT 1
) cta ON TRUE
LEFT JOIN LATERAL (
  SELECT name, acreage,
         ST_Distance(location, b.location::geography)::INT AS distance_m
  FROM {{ source('silver', 'parks') }}
  ORDER BY location <-> b.location::geography
  LIMIT 1
) p ON TRUE
