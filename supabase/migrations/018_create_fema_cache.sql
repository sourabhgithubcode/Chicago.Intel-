-- Migration 018 — FEMA flood zone per-address cache
--
-- FEMA's NFHL ArcGIS endpoint is free + keyless but rate-limited; cache
-- per coordinate (rounded to 4 decimal places ≈ 11m precision) for 1yr
-- since FIRMs update infrequently.
--
-- Endpoint: https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query
-- Returns: FLD_ZONE (e.g. "X", "AE", "VE") + ZONE_SUBTY (description).

CREATE TABLE IF NOT EXISTS fema_cache (
  coord_key     TEXT PRIMARY KEY,   -- "{lat:.4f},{lng:.4f}"
  flood_zone    TEXT,                -- FEMA code: A/AE/AH/AO/V/VE/X/D/null
  zone_subtype  TEXT,                -- e.g. "AREA OF MINIMAL FLOOD HAZARD"
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE fema_cache ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS anon_select_fema_cache ON fema_cache;
CREATE POLICY anon_select_fema_cache ON fema_cache
  FOR SELECT TO anon USING (true);
