-- Migration 033 — amenity coordinates for map pins
--
-- The /amenities endpoint (treasurer_service.py) fetches Overpass results with
-- `out center` (so lat/lon are available) but only cached name + distance. Add
-- coordinate columns so the building-view map can pin each amenity at its exact
-- location. Idempotent.

ALTER TABLE amenities_cache
  ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION;
