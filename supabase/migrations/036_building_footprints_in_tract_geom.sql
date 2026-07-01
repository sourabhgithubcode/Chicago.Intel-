-- Migration 036 — building_footprints_in_tract: geometry exact-test (035 was
-- still slow because the buildings range test ran in GEOGRAPHY space).
--
-- Diagnosis (measured): the geography GIST `&&` bbox prefilter works fine, but
-- `ST_Intersects(b.location, tract::geography)` costs ~3ms PER candidate against
-- the complex tract polygon → 3-8s for 800-1000 buildings (both 032 and 035 hit
-- this). find_building_at (KNN) stays fast because it never range-scans.
--
-- Fix: keep the geography `&&` bbox prefilter (uses the buildings geography
-- GIST), but do the exact point-in-polygon in GEOMETRY space
-- (ST_Contains(tract.geometry, b.location::geometry)) — 10-50x cheaper than the
-- geography test. Footprint join already used geometry ST_Contains. Same RETURNS
-- shape — frontend getBuildingsInTract is unchanged.
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
  WITH t AS (
    SELECT geometry AS gm, geometry::geography AS gg
    FROM tracts WHERE id = p_geoid
  ),
  b_in AS (
    SELECT b.location::geometry AS pt, b.address,
           b.violations_5yr, b.heat_complaints, b.bug_reports, b.year_built
    FROM buildings b, t
    WHERE b.location && t.gg                        -- geography GIST bbox prefilter
      AND ST_Contains(t.gm, b.location::geometry)   -- cheap GEOMETRY point-in-polygon
  ),
  joined AS (
    SELECT f.bldg_id, f.geometry AS fgm,
           b_in.address, b_in.violations_5yr, b_in.heat_complaints,
           b_in.bug_reports, b_in.year_built
    FROM b_in
    JOIN building_footprints f
      ON f.geometry && b_in.pt
     AND ST_Contains(f.geometry, b_in.pt)
  )
  SELECT bldg_id, ST_AsGeoJSON(fgm)::json AS geom,
         MIN(address)         AS address,
         MAX(violations_5yr)  AS violations_5yr,
         MAX(heat_complaints) AS heat_complaints,
         MAX(bug_reports)     AS bug_reports,
         MAX(year_built)      AS year_built
  FROM joined
  GROUP BY bldg_id, fgm
  LIMIT 4000;
$$;
