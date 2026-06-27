-- Migration 027 — fix SRID-0 bug in point-in-polygon RPCs
--
-- cca_containing_point / tract_containing_point (005) and displacement_at (020)
-- build the test point with ST_MakePoint(lng, lat), which yields SRID 0. The
-- polygon columns are geometry(...,4326), so ST_Contains raised
--   "Operation on mixed SRID geometries (MultiPolygon, 4326) != (Point, 0)"
-- on every call — i.e. these RPCs have always errored in prod. The frontend's
-- static-bundle fallback (ccaStatic/tractStatic) masked it, but that uses
-- simplified geometry and can misclassify points near CCA/tract borders.
-- Wrapping the point in ST_SetSRID(...,4326) makes containment work on the
-- exact polygons. Signatures and return types are unchanged.

CREATE OR REPLACE FUNCTION cca_containing_point(lat FLOAT, lng FLOAT)
RETURNS TABLE(id INT, name TEXT)
LANGUAGE sql STABLE AS $$
  SELECT id, name FROM ccas
  WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint(lng, lat), 4326))
  LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION tract_containing_point(lat FLOAT, lng FLOAT)
RETURNS TABLE(id TEXT, name TEXT, cca_id INT)
LANGUAGE sql STABLE AS $$
  SELECT id, name, cca_id FROM tracts
  WHERE ST_Contains(geometry, ST_SetSRID(ST_MakePoint(lng, lat), 4326))
  LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION displacement_at(lat FLOAT, lng FLOAT)
RETURNS TABLE(geoid TEXT, typology TEXT)
LANGUAGE sql STABLE AS $$
  SELECT t.id, d.typology
  FROM tracts t
  JOIN displacement_typology d ON d.geoid = t.id
  WHERE ST_Contains(t.geometry, ST_SetSRID(ST_MakePoint(lng, lat), 4326))
  LIMIT 1;
$$;
