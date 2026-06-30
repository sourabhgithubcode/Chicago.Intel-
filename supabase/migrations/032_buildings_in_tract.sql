-- Migration 032 — buildings within a tract (for the tract-level building layer)
--
-- The tract-level map shades individual buildings by a building-specific metric
-- (violations / heat / bed-bug complaints, year built). buildings has no
-- tract_id, so select spatially. b.location is geography(Point) with a GIST
-- index → ST_Intersects against the tract polygon cast to geography uses it.
-- LANGUAGE sql STABLE; executable by PUBLIC (anon) like the other geometry RPCs.

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
  FROM tracts t
  JOIN buildings b ON ST_Intersects(b.location, t.geometry::geography)
  WHERE t.id = p_geoid
  LIMIT 4000;
$$;
