-- Migration 032 — buildings within a tract (for the tract-level building layer)
--
-- The tract-level map shades individual buildings by a building-specific metric
-- (violations / heat / bed-bug complaints, year built). buildings has no
-- tract_id, so select spatially. b.location is geography(Point) with a GIST
-- index → ST_Intersects against the tract polygon cast to geography uses it.
-- LANGUAGE sql STABLE; executable by PUBLIC (anon) like the other geometry RPCs.

-- The tract polygon is fetched ONCE as a scalar geography subquery so the
-- planner index-scans buildings.location (GIST) instead of seq-scanning all
-- 856k rows. The JOIN form seq-scanned and hit the statement timeout.
CREATE OR REPLACE FUNCTION buildings_in_tract(p_geoid TEXT)
RETURNS TABLE (
  pin            TEXT,
  lng            FLOAT,
  lat            FLOAT,
  violations_5yr INT,
  heat_complaints INT,
  bug_reports    INT,
  year_built     INT
)
LANGUAGE sql STABLE AS $$
  SELECT b.pin,
         ST_X(b.location::geometry), ST_Y(b.location::geometry),
         b.violations_5yr, b.heat_complaints, b.bug_reports, b.year_built
  FROM buildings b
  WHERE b.location && (SELECT geometry::geography FROM tracts WHERE id = p_geoid)
    AND ST_Intersects(b.location, (SELECT geometry::geography FROM tracts WHERE id = p_geoid))
  LIMIT 4000;
$$;
