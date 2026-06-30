-- Migration 034 — building footprints within a tract (metric-colored fill)
--
-- The tract layer shaded buildings as centroid DOTS (032). We have the real
-- footprints in building_footprints (820k MultiPolygons, GIST index from 029),
-- but that table has only bldg_id + geometry — no PIN, no metrics. The metrics
-- live in buildings (keyed by PIN). The two share no key, so join SPATIALLY: a
-- footprint "owns" the buildings whose point falls inside it. Condos (many PINs,
-- one footprint) collapse to the footprint, aggregated via MAX.
--
-- Driven from building_footprints filtered to the tract bbox (its geometry
-- GIST), then ST_Covers against buildings.location (geography GIST) per
-- footprint. Footprints with no matching building are dropped (INNER JOIN).
-- LANGUAGE sql STABLE; executable by PUBLIC (anon) like the other geometry RPCs.
CREATE OR REPLACE FUNCTION building_footprints_in_tract(p_geoid TEXT)
RETURNS TABLE (
  bldg_id         BIGINT,
  geom            JSON,
  address         TEXT,
  violations_5yr  INT,
  heat_complaints INT,
  bug_reports     INT,
  year_built      INT
)
LANGUAGE sql STABLE AS $$
  WITH t AS (SELECT geometry AS g FROM tracts WHERE id = p_geoid),
  fp AS (
    SELECT f.bldg_id, f.geometry
    FROM building_footprints f
    WHERE f.geometry && (SELECT g FROM t)
      AND ST_Intersects(f.geometry, (SELECT g FROM t))
  ),
  agg AS (
    SELECT fp.bldg_id,
           MIN(b.address)         AS address,
           MAX(b.violations_5yr)  AS violations_5yr,
           MAX(b.heat_complaints) AS heat_complaints,
           MAX(b.bug_reports)     AS bug_reports,
           MAX(b.year_built)      AS year_built
    FROM fp
    JOIN buildings b
      ON fp.geometry::geography && b.location
     AND ST_Covers(fp.geometry::geography, b.location)
    GROUP BY fp.bldg_id
  )
  SELECT fp.bldg_id, ST_AsGeoJSON(fp.geometry)::json, agg.address,
         agg.violations_5yr, agg.heat_complaints, agg.bug_reports, agg.year_built
  FROM fp JOIN agg USING (bldg_id)
  LIMIT 4000;
$$;
