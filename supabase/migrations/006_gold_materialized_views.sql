-- Gold layer: materialized views that pre-join silver tables.
-- Frontend reads ONE row per address lookup instead of 5+ joins.
-- Refreshed at end of quarterly pipeline via REFRESH MATERIALIZED VIEW.

-- ─── gold_address_intel ────────────────────────────────
-- One row per building with CCA, tract, nearest CTA, nearest park pre-joined.
DROP MATERIALIZED VIEW IF EXISTS gold_address_intel CASCADE;

CREATE MATERIALIZED VIEW gold_address_intel AS
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
     FROM cpd_incidents
     WHERE ST_DWithin(location, b.location::geography, 402)
       AND date >= NOW() - INTERVAL '5 years')          AS violent_5yr,
  (SELECT COUNT(*) FILTER (WHERE type = 'property')::INT
     FROM cpd_incidents
     WHERE ST_DWithin(location, b.location::geography, 402)
       AND date >= NOW() - INTERVAL '5 years')          AS property_5yr,

  NOW() AS refreshed_at

FROM buildings b
LEFT JOIN ccas cca  ON ST_Contains(cca.geometry, b.location)
LEFT JOIN tracts t  ON ST_Contains(t.geometry,  b.location)
LEFT JOIN LATERAL (
  SELECT name, lines,
         ST_Distance(location, b.location::geography)::INT AS distance_m
  FROM cta_stops
  ORDER BY location <-> b.location::geography
  LIMIT 1
) cta ON TRUE
LEFT JOIN LATERAL (
  SELECT name, acreage,
         ST_Distance(location, b.location::geography)::INT AS distance_m
  FROM parks
  ORDER BY location <-> b.location::geography
  LIMIT 1
) p ON TRUE;

-- Unique index required for REFRESH ... CONCURRENTLY (no downtime during refresh)
CREATE UNIQUE INDEX idx_gold_address_pin     ON gold_address_intel(pin);
CREATE INDEX        idx_gold_address_location ON gold_address_intel USING GIST(location);
CREATE INDEX        idx_gold_address_norm     ON gold_address_intel(address_norm);
CREATE INDEX        idx_gold_address_cca      ON gold_address_intel(cca_id);

-- ─── gold_cca_summary ──────────────────────────────────
-- One row per Community Area for the zoom-10 to 12 map layer.
DROP MATERIALIZED VIEW IF EXISTS gold_cca_summary CASCADE;

CREATE MATERIALIZED VIEW gold_cca_summary AS
SELECT
  c.id,
  c.name,
  c.geometry,
  c.rent_median,
  c.safety_score,
  c.walk_score,
  c.disp_score,

  COUNT(DISTINCT b.pin)                                    AS building_count,
  COALESCE(AVG(b.landlord_score), 0)::NUMERIC(4,2)         AS avg_landlord_score,
  COUNT(DISTINCT b.pin) FILTER (WHERE b.tax_current = FALSE) AS delinquent_buildings,

  (SELECT COUNT(*) FILTER (WHERE ci.type = 'violent')::INT
     FROM cpd_incidents ci
     WHERE ST_Contains(c.geometry, ci.location)
       AND ci.date >= NOW() - INTERVAL '1 year')           AS violent_1yr,

  NOW() AS refreshed_at

FROM ccas c
LEFT JOIN buildings b ON ST_Contains(c.geometry, b.location)
GROUP BY c.id, c.name, c.geometry, c.rent_median,
         c.safety_score, c.walk_score, c.disp_score;

CREATE UNIQUE INDEX idx_gold_cca_id       ON gold_cca_summary(id);
CREATE INDEX        idx_gold_cca_geometry ON gold_cca_summary USING GIST(geometry);

-- ─── gold_tract_summary ────────────────────────────────
-- One row per census tract for the zoom-12 to 14 map layer.
DROP MATERIALIZED VIEW IF EXISTS gold_tract_summary CASCADE;

CREATE MATERIALIZED VIEW gold_tract_summary AS
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

  COUNT(DISTINCT b.pin)                                    AS building_count,
  COALESCE(AVG(b.landlord_score), 0)::NUMERIC(4,2)         AS avg_landlord_score,

  NOW() AS refreshed_at

FROM tracts t
LEFT JOIN buildings b ON ST_Contains(t.geometry, b.location)
GROUP BY t.id, t.cca_id, t.name, t.geometry, t.rent_median, t.rent_moe,
         t.safety_score, t.walk_score, t.population, t.disp_score;

CREATE UNIQUE INDEX idx_gold_tract_id       ON gold_tract_summary(id);
CREATE INDEX        idx_gold_tract_cca      ON gold_tract_summary(cca_id);
CREATE INDEX        idx_gold_tract_geometry ON gold_tract_summary USING GIST(geometry);

-- ─── Refresh helper ────────────────────────────────────
-- Called by the pipeline after silver load completes.
-- Uses CONCURRENTLY so frontend reads never see an empty state.
CREATE OR REPLACE FUNCTION refresh_gold_layer()
RETURNS VOID
LANGUAGE plpgsql AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY gold_address_intel;
  REFRESH MATERIALIZED VIEW CONCURRENTLY gold_cca_summary;
  REFRESH MATERIALIZED VIEW CONCURRENTLY gold_tract_summary;
END;
$$;
