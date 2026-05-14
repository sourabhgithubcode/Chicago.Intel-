-- Migration 021 — GeoJSON geometry accessors for map layer switching
--
-- MapView.jsx needs GeoJSON (not WKB) to drive react-map-gl Source data.
-- cca_containing_point / tract_containing_point already return id/name;
-- these two RPCs return the matching polygon geometry as GeoJSON.

CREATE OR REPLACE FUNCTION cca_geojson(cca_id INT)
RETURNS JSON LANGUAGE sql STABLE AS $$
  SELECT ST_AsGeoJSON(geometry)::JSON FROM ccas WHERE id = cca_id LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION tract_geojson(geoid TEXT)
RETURNS JSON LANGUAGE sql STABLE AS $$
  SELECT ST_AsGeoJSON(geometry)::JSON FROM tracts WHERE id = geoid LIMIT 1;
$$;
