-- Performance indexes — critical for radius queries
-- NEVER remove GIST indexes on location columns

CREATE INDEX IF NOT EXISTS idx_cpd_location
  ON cpd_incidents USING GIST(location);

CREATE INDEX IF NOT EXISTS idx_cpd_date
  ON cpd_incidents(date);

CREATE INDEX IF NOT EXISTS idx_cpd_type
  ON cpd_incidents(type);

CREATE INDEX IF NOT EXISTS idx_buildings_location
  ON buildings USING GIST(location);

CREATE INDEX IF NOT EXISTS idx_buildings_address
  ON buildings(address_norm);

CREATE INDEX IF NOT EXISTS idx_cta_location
  ON cta_stops USING GIST(location);

CREATE INDEX IF NOT EXISTS idx_parks_location
  ON parks USING GIST(location);

CREATE INDEX IF NOT EXISTS idx_tracts_cca
  ON tracts(cca_id);

CREATE INDEX IF NOT EXISTS idx_tracts_geometry
  ON tracts USING GIST(geometry);

CREATE INDEX IF NOT EXISTS idx_ccas_geometry
  ON ccas USING GIST(geometry);

CREATE INDEX IF NOT EXISTS idx_amenities_address
  ON amenities_cache(address_key, category);

CREATE INDEX IF NOT EXISTS idx_amenities_expires
  ON amenities_cache(expires_at);
