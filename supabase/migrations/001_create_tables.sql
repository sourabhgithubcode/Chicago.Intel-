-- Chicago.Intel Database Schema
-- Run in order: 001 → 002 → 003 → 004

-- Enable PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;

-- Layer 1: Community Areas (77 rows)
CREATE TABLE IF NOT EXISTS ccas (
  id              INT PRIMARY KEY,
  name            TEXT NOT NULL,
  rent_median     INT,
  safety_score    NUMERIC(4,2),
  walk_score      NUMERIC(4,2),
  run_score       NUMERIC(4,2),
  vibe_score      NUMERIC(4,2),
  disp_score      NUMERIC(4,2),
  geometry        GEOMETRY(MULTIPOLYGON, 4326),
  data_vintage    TEXT DEFAULT '2019-23',
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Layer 2: Census Tracts (~800 rows for Cook County Chicago)
CREATE TABLE IF NOT EXISTS tracts (
  id              TEXT PRIMARY KEY,
  cca_id          INT REFERENCES ccas(id),
  name            TEXT,
  rent_median     INT,
  rent_moe        INT,
  safety_score    NUMERIC(4,2),
  walk_score      NUMERIC(4,2),
  population      INT,
  disp_score      NUMERIC(4,2),
  geometry        GEOMETRY(MULTIPOLYGON, 4326),
  data_vintage    TEXT DEFAULT '2019-23',
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Layer 3: CPD Incidents (300K+ rows)
CREATE TABLE IF NOT EXISTS cpd_incidents (
  id              BIGINT PRIMARY KEY,
  iucr            TEXT,
  type            TEXT CHECK (type IN ('violent', 'property', 'other')),
  description     TEXT,
  date            DATE NOT NULL,
  location        GEOMETRY(POINT, 4326),
  year            INT GENERATED ALWAYS AS (EXTRACT(YEAR FROM date)::INT) STORED
);

-- Layer 3: 311 Complaints
CREATE TABLE IF NOT EXISTS complaints_311 (
  id              BIGINT PRIMARY KEY,
  type            TEXT,
  address         TEXT,
  date            DATE,
  location        GEOMETRY(POINT, 4326)
);

-- Layer 3: CTA Stops
CREATE TABLE IF NOT EXISTS cta_stops (
  id              INT PRIMARY KEY,
  name            TEXT NOT NULL,
  lines           TEXT[],
  accessible      BOOLEAN DEFAULT FALSE,
  location        GEOMETRY(POINT, 4326)
);

-- Layer 3: Parks
CREATE TABLE IF NOT EXISTS parks (
  id              INT PRIMARY KEY,
  name            TEXT NOT NULL,
  acreage         NUMERIC(8,2),
  location        GEOMETRY(POINT, 4326),
  boundary        GEOMETRY(MULTIPOLYGON, 4326)
);

-- Layer 4: Buildings (Cook County Assessor parcel data)
CREATE TABLE IF NOT EXISTS buildings (
  pin             TEXT PRIMARY KEY,
  address         TEXT NOT NULL,
  address_norm    TEXT,
  owner           TEXT,
  year_built      INT,
  purchase_year   INT,
  purchase_price  BIGINT,
  tax_current     BOOLEAN,
  tax_annual      INT,
  violations_5yr  INT DEFAULT 0,
  heat_complaints INT DEFAULT 0,
  bug_reports     INT DEFAULT 0,
  landlord_score  NUMERIC(4,2),
  flood_zone      TEXT,
  school_elem     TEXT,
  location        GEOMETRY(POINT, 4326),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Amenity cache (Google Places results — cached 30 days)
CREATE TABLE IF NOT EXISTS amenities_cache (
  id              BIGSERIAL PRIMARY KEY,
  address_key     TEXT NOT NULL,
  category        TEXT NOT NULL,
  name            TEXT,
  distance_m      INT,
  price_level     INT,
  place_id        TEXT,
  location        GEOMETRY(POINT, 4326),
  cached_at       TIMESTAMPTZ DEFAULT NOW(),
  expires_at      TIMESTAMPTZ DEFAULT NOW() + INTERVAL '30 days'
);
