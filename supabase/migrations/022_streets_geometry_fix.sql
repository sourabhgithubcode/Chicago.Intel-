-- Migration 022 — Fix streets.geometry column type
--
-- Migration 007 now declares GEOMETRY(MULTILINESTRING,4326) but the live table
-- was created when the column was LINESTRING. The Chicago street centerline
-- source (Socrata 6imu-meau) emits MultiLineString for all segments, so LINESTRING
-- rejects every row. This migration corrects the column type.
--
-- Safe to run when streets is empty (first bronze replay).
-- When streets is populated: PostGIS allows ALTER TYPE on the same geometry
-- family (Line → MultiLine) only if the existing data can be implicitly cast;
-- this migration adds a USING clause to force the cast for safety.

ALTER TABLE streets
  ALTER COLUMN geometry
  TYPE GEOMETRY(MULTILINESTRING, 4326)
  USING geometry::GEOMETRY(MULTILINESTRING, 4326);
