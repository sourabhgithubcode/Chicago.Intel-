-- Additive migration: pipeline audit table, address_norm on 311, missing indexes,
-- and additional RPC functions (purchase fields, CCA/tract lookup).
-- Safe to re-run — uses IF NOT EXISTS / CREATE OR REPLACE / ADD COLUMN IF NOT EXISTS.

-- ─── Add normalized address column to 311 ──────────────
ALTER TABLE complaints_311
  ADD COLUMN IF NOT EXISTS address_norm TEXT;

-- ─── Pipeline audit trail ──────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
  id              BIGSERIAL PRIMARY KEY,
  run_id          TEXT UNIQUE NOT NULL,
  started_at      TIMESTAMPTZ DEFAULT NOW(),
  completed_at    TIMESTAMPTZ,
  status          TEXT CHECK (status IN ('running', 'success', 'failed', 'rolled_back')),
  sources         TEXT[],
  row_counts      JSONB,
  error_message   TEXT
);

-- ─── Missing indexes ───────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_buildings_landlord
  ON buildings(landlord_score);

CREATE INDEX IF NOT EXISTS idx_311_address
  ON complaints_311(address_norm);

CREATE INDEX IF NOT EXISTS idx_311_location
  ON complaints_311 USING GIST(location);

CREATE INDEX IF NOT EXISTS idx_311_date
  ON complaints_311(date);

CREATE INDEX IF NOT EXISTS idx_pipeline_run_id
  ON pipeline_runs(run_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_status
  ON pipeline_runs(status);

-- ─── Extend find_building_at with purchase fields ──────
-- DROP first: OR REPLACE alone fails when the return type changes
-- (Postgres 42P13). 003 created this with a narrower return shape; 005
-- widens it with purchase_year + purchase_price.
DROP FUNCTION IF EXISTS find_building_at(double precision, double precision) CASCADE;

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
  SELECT
    pin, address, owner, year_built, purchase_year, purchase_price,
    tax_current, tax_annual,
    violations_5yr, heat_complaints, bug_reports,
    landlord_score, flood_zone, school_elem,
    ST_Distance(location, ST_MakePoint(lng, lat)::geography)::INT
  FROM buildings
  WHERE ST_DWithin(location, ST_MakePoint(lng, lat)::geography, 100)
  ORDER BY location <-> ST_MakePoint(lng, lat)::geography
  LIMIT 1;
$$;

-- ─── CCA/tract containment lookups ─────────────────────
CREATE OR REPLACE FUNCTION cca_containing_point(lat FLOAT, lng FLOAT)
RETURNS TABLE(id INT, name TEXT)
LANGUAGE sql STABLE AS $$
  SELECT id, name FROM ccas
  WHERE ST_Contains(geometry, ST_MakePoint(lng, lat)::geometry)
  LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION tract_containing_point(lat FLOAT, lng FLOAT)
RETURNS TABLE(id TEXT, name TEXT, cca_id INT)
LANGUAGE sql STABLE AS $$
  SELECT id, name, cca_id FROM tracts
  WHERE ST_Contains(geometry, ST_MakePoint(lng, lat)::geometry)
  LIMIT 1;
$$;
