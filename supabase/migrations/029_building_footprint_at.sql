-- Migration 029 — exact building-footprint highlight for the map
--
-- MapView highlights a generic 75 m circle when Mapbox's vector-tile "building"
-- layer has no footprint at the point. We have the real footprints in
-- building_footprints (820k MultiPolygons), so return the actual one and draw
-- that instead. The table was created out-of-band and has NO spatial index, so
-- a nearest-footprint query would scan all rows; add a GIST index first.
--
-- SECURITY DEFINER so the anon frontend can read the footprint without opening
-- a broad RLS policy on the whole table. KNN (<->) uses the new GIST index;
-- only the single nearest row is cast to geography for the 60 m cutoff.

CREATE INDEX IF NOT EXISTS idx_building_footprints_geom
  ON building_footprints USING GIST(geometry);

CREATE OR REPLACE FUNCTION building_footprint_at(lat FLOAT, lng FLOAT)
RETURNS JSON
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  WITH p AS (SELECT ST_SetSRID(ST_MakePoint(lng, lat), 4326) AS g),
  nearest AS (
    SELECT geometry AS gm,
           ST_Distance(geometry::geography, (SELECT g FROM p)::geography) AS dm
    FROM building_footprints
    ORDER BY geometry <-> (SELECT g FROM p)   -- KNN → uses GIST index
    LIMIT 1
  )
  SELECT ST_AsGeoJSON(gm)::JSON FROM nearest WHERE dm <= 60;
$$;
