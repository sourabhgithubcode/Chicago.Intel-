-- Migration 035 — speed up building_footprints_in_tract (034 hit the timeout)
--
-- 034 drove from building_footprints and did ST_Covers(f.geometry::geography,
-- b.location) per footprint. Casting 820k-row MultiPolygons to geography is too
-- slow and exceeded the statement timeout (57014) on dense tracts.
--
-- Reverse the drive: first get the tract's buildings via buildings.location
-- geography GIST (the proven-fast pattern from 032), then for each building
-- POINT find its footprint via the building_footprints geometry GIST
-- (point-in-polygon, index-backed). Condos (many points → one footprint)
-- aggregate via MAX. Same RETURNS shape — frontend getBuildingsInTract is
-- unchanged. CREATE OR REPLACE supersedes the 034 definition.
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
  b_in AS (
    SELECT b.location::geometry AS pt, b.address,
           b.violations_5yr, b.heat_complaints, b.bug_reports, b.year_built
    FROM buildings b
    WHERE b.location && (SELECT g FROM t)::geography
      AND ST_Intersects(b.location, (SELECT g FROM t)::geography)
  ),
  joined AS (
    SELECT f.bldg_id, f.geometry AS gm,
           b_in.address, b_in.violations_5yr, b_in.heat_complaints,
           b_in.bug_reports, b_in.year_built
    FROM b_in
    JOIN building_footprints f
      ON f.geometry && b_in.pt
     AND ST_Contains(f.geometry, b_in.pt)
  )
  SELECT bldg_id, ST_AsGeoJSON(gm)::json AS geom,
         MIN(address)         AS address,
         MAX(violations_5yr)  AS violations_5yr,
         MAX(heat_complaints) AS heat_complaints,
         MAX(bug_reports)     AS bug_reports,
         MAX(year_built)      AS year_built
  FROM joined
  GROUP BY bldg_id, gm
  LIMIT 4000;
$$;
