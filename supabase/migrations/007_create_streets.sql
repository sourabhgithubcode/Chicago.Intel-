-- Migration 007 — Streets layer
--
-- Adds the 4th data layer between Tract and Building. See docs/DATA_DICTIONARY.md §2
-- for the full spec.
--
-- This migration adds:
--   1. streets table + indexes
--   2. buildings.street_id FK + index
--   3. Two spatial-assignment functions (called by reconcile pipeline)
--   4. gold_street_summary materialized view
--   5. Updated refresh_gold_layer() to include the new view
--
-- gold_address_intel is NOT modified here. It will gain a street_id column in a
-- later migration after reconcile has populated buildings.street_id, so the
-- existing materialized view keeps serving reads during the transition.
--
-- Idempotent: uses IF NOT EXISTS / CREATE OR REPLACE / ADD COLUMN IF NOT EXISTS.

-- ─── 1. streets table ─────────────────────────────────
-- One row per centerline segment. Source: Chicago Data Portal 6imu-meau (Socrata).
CREATE TABLE IF NOT EXISTS streets (
  id           TEXT PRIMARY KEY,            -- street_id from source
  name         TEXT NOT NULL,               -- "N Lincoln Ave" (pre_dir + name + type + suf_dir)
  name_norm    TEXT,                        -- normalized for joins
  from_addr    INT,                         -- min(l_f_add, r_f_add)
  to_addr      INT,                         -- max(l_t_add, r_t_add)
  cca_id       INT REFERENCES ccas(id),     -- assigned by assign_streets_to_polygons()
  tract_id     TEXT REFERENCES tracts(id),  -- assigned by assign_streets_to_polygons()
  geometry     GEOMETRY(MULTILINESTRING, 4326)  -- source emits MultiLineString
);

CREATE INDEX IF NOT EXISTS idx_streets_geometry  ON streets USING GIST(geometry);
CREATE INDEX IF NOT EXISTS idx_streets_name_norm ON streets(name_norm);
CREATE INDEX IF NOT EXISTS idx_streets_cca       ON streets(cca_id);
CREATE INDEX IF NOT EXISTS idx_streets_tract     ON streets(tract_id);

-- ─── 2. buildings.street_id FK ────────────────────────
-- Nullable. Populated by assign_buildings_to_streets() in the reconcile step.
ALTER TABLE buildings ADD COLUMN IF NOT EXISTS street_id TEXT REFERENCES streets(id);
CREATE INDEX IF NOT EXISTS idx_buildings_street ON buildings(street_id);

-- ─── 3. Spatial-assignment functions ──────────────────
-- Called by scripts/reconcile.py after streets silver load, before gold refresh.
-- Both are idempotent — re-running produces the same result.

-- 3a. Assign cca_id and tract_id on every street.
-- ST_Contains(polygon, linestring) is rarely true (segments often straddle
-- boundaries). Sample a representative point on the segment via ST_PointOnSurface
-- (always returns a point ON the geometry) and test polygon containment of that
-- point. This makes assignment deterministic for boundary-crossing streets.
CREATE OR REPLACE FUNCTION assign_streets_to_polygons()
RETURNS TABLE(streets_with_cca INT, streets_with_tract INT)
LANGUAGE plpgsql AS $$
DECLARE
  n_cca   INT;
  n_tract INT;
BEGIN
  UPDATE streets s
     SET cca_id = c.id
    FROM ccas c
   WHERE ST_Contains(c.geometry, ST_PointOnSurface(s.geometry));
  GET DIAGNOSTICS n_cca = ROW_COUNT;

  UPDATE streets s
     SET tract_id = t.id
    FROM tracts t
   WHERE ST_Contains(t.geometry, ST_PointOnSurface(s.geometry));
  GET DIAGNOSTICS n_tract = ROW_COUNT;

  RETURN QUERY SELECT n_cca, n_tract;
END;
$$;

-- 3b. Assign street_id on every building.
-- KNN with a 30m max distance — matches §5 aggregation rule. The GIST index on
-- streets.geometry makes the <-> ordering fast; the geography cast in
-- ST_DWithin gives us meter-accurate distance filtering.
CREATE OR REPLACE FUNCTION assign_buildings_to_streets()
RETURNS INT
LANGUAGE plpgsql AS $$
DECLARE
  n_updated INT;
BEGIN
  UPDATE buildings b
     SET street_id = (
       SELECT s.id
         FROM streets s
        WHERE ST_DWithin(s.geometry::geography, b.location::geography, 30)
        ORDER BY s.geometry <-> b.location
        LIMIT 1
     );
  GET DIAGNOSTICS n_updated = ROW_COUNT;
  RETURN n_updated;
END;
$$;

-- ─── 4. gold_street_summary ───────────────────────────
-- One row per street segment for the zoom-14 to 16 map layer and the §9.7
-- comparison surface (Street panel).
DROP MATERIALIZED VIEW IF EXISTS gold_street_summary CASCADE;

CREATE MATERIALIZED VIEW gold_street_summary AS
SELECT
  s.id,
  s.name,
  s.name_norm,
  s.from_addr,
  s.to_addr,
  s.cca_id,
  s.tract_id,
  s.geometry,

  -- Building aggregates (NULL until reconcile populates buildings.street_id)
  COUNT(DISTINCT b.pin)::INT                                      AS building_count,
  COALESCE(AVG(b.landlord_score), 0)::NUMERIC(4,2)                AS avg_landlord_score,
  mode() WITHIN GROUP (ORDER BY b.flood_zone)
    FILTER (WHERE b.flood_zone IS NOT NULL)                       AS flood_zone_modal,

  -- Crime within 100m of segment (§5 rule for Street layer)
  (SELECT COUNT(*)::INT FROM cpd_incidents ci
     WHERE ST_DWithin(ci.location, s.geometry::geography, 100)
       AND ci.type = 'violent'
       AND ci.date >= NOW() - INTERVAL '5 years')                 AS violent_5yr,
  (SELECT COUNT(*)::INT FROM cpd_incidents ci
     WHERE ST_DWithin(ci.location, s.geometry::geography, 100)
       AND ci.type = 'property'
       AND ci.date >= NOW() - INTERVAL '5 years')                 AS property_5yr,

  -- 311 within 100m of segment
  (SELECT COUNT(*)::INT FROM complaints_311 c
     WHERE ST_DWithin(c.location, s.geometry::geography, 100)
       AND c.date >= NOW() - INTERVAL '5 years')                  AS complaints_311_5yr,

  -- Modal Google Places price tier within 0.25mi (signal, not precise)
  (SELECT mode() WITHIN GROUP (ORDER BY a.price_level)
     FROM amenities_cache a
     WHERE a.category = 'grocery'
       AND a.price_level IS NOT NULL
       AND ST_DWithin(a.location, s.geometry::geography, 402))    AS grocery_tier_modal,
  (SELECT mode() WITHIN GROUP (ORDER BY a.price_level)
     FROM amenities_cache a
     WHERE a.category = 'restaurant'
       AND a.price_level IS NOT NULL
       AND ST_DWithin(a.location, s.geometry::geography, 402))    AS dining_tier_modal,

  -- Nearest CTA stop from segment centroid (KNN)
  cta.name                                                        AS nearest_cta_name,
  cta.distance_m                                                  AS nearest_cta_m,

  NOW()                                                           AS refreshed_at

FROM streets s
LEFT JOIN buildings b ON b.street_id = s.id
LEFT JOIN LATERAL (
  SELECT cs.name,
         ST_Distance(cs.location, ST_Centroid(s.geometry)::geography)::INT AS distance_m
    FROM cta_stops cs
   ORDER BY cs.location <-> ST_Centroid(s.geometry)::geography
   LIMIT 1
) cta ON TRUE
GROUP BY s.id, s.name, s.name_norm, s.from_addr, s.to_addr,
         s.cca_id, s.tract_id, s.geometry,
         cta.name, cta.distance_m;

-- Unique index required for REFRESH ... CONCURRENTLY (zero-downtime refresh)
CREATE UNIQUE INDEX idx_gold_street_id       ON gold_street_summary(id);
CREATE INDEX        idx_gold_street_geometry ON gold_street_summary USING GIST(geometry);
CREATE INDEX        idx_gold_street_cca      ON gold_street_summary(cca_id);
CREATE INDEX        idx_gold_street_tract    ON gold_street_summary(tract_id);

-- ─── 5. Update refresh_gold_layer() to include the new view ──
-- gold_street_summary's first refresh must be non-concurrent (CONCURRENTLY
-- requires at least one prior population). The orchestrator will call this
-- function on its next run; the very first call after deploying this migration
-- needs to be `REFRESH MATERIALIZED VIEW gold_street_summary` (no CONCURRENTLY)
-- once, before this function is invoked. Document this in the runbook.
CREATE OR REPLACE FUNCTION refresh_gold_layer()
RETURNS VOID
LANGUAGE plpgsql AS $$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY gold_address_intel;
  REFRESH MATERIALIZED VIEW CONCURRENTLY gold_street_summary;
  REFRESH MATERIALIZED VIEW CONCURRENTLY gold_cca_summary;
  REFRESH MATERIALIZED VIEW CONCURRENTLY gold_tract_summary;
END;
$$;
