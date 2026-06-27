-- Migration 028 — make find_building_at fast (use the geometry GIST index)
--
-- buildings.location is GEOMETRY(POINT,4326) with a geometry GIST index
-- (idx_buildings_location, migration 002). The old find_building_at compared
-- and ordered by location::geography, which forces a per-row cast and prevents
-- the geometry index from being used → sequential scan of ~858K rows → the
-- query exceeds the anon role's 3s statement_timeout, so building searches
-- intermittently fail with "We had trouble loading data."
--
-- Fix: do the nearest-neighbour search with the geometry <-> operator (this
-- IS index-backed), take the single nearest row, then cast only that one row
-- to geography for an accurate metre distance and apply the 100 m cutoff.
-- Signature/return columns are identical to migration 005.

CREATE OR REPLACE FUNCTION find_building_at(lat FLOAT, lng FLOAT)
RETURNS TABLE(
  pin TEXT, address TEXT, owner TEXT, year_built INT,
  purchase_year INT, purchase_price BIGINT,
  tax_current BOOLEAN, tax_annual INT,
  violations_5yr INT, heat_complaints INT, bug_reports INT,
  landlord_score NUMERIC, flood_zone TEXT, school_elem TEXT,
  distance_m INT
)
LANGUAGE sql STABLE AS $$
  WITH p AS (SELECT ST_SetSRID(ST_MakePoint(lng, lat), 4326) AS g),
  nearest AS (
    SELECT b.pin, b.address, b.owner, b.year_built, b.purchase_year, b.purchase_price,
           b.tax_current, b.tax_annual, b.violations_5yr, b.heat_complaints, b.bug_reports,
           b.landlord_score, b.flood_zone, b.school_elem,
           ST_Distance(b.location::geography, (SELECT g FROM p)::geography) AS dm
    FROM buildings b
    ORDER BY b.location <-> (SELECT g FROM p)   -- geometry KNN → uses GIST index
    LIMIT 1
  )
  SELECT pin, address, owner, year_built, purchase_year, purchase_price,
         tax_current, tax_annual, violations_5yr, heat_complaints, bug_reports,
         landlord_score, flood_zone, school_elem, dm::INT
  FROM nearest
  WHERE dm <= 100;
$$;
