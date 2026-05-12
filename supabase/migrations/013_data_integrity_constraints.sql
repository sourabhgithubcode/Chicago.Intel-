-- Migration 013 — Data integrity constraints
--
-- Adds CHECK + NOT-NULL constraints + an advisory-lock helper for source
-- isolation. Spec: DATA_DICTIONARY.md §15.
--
-- All CHECK constraints use `NOT VALID` so existing rows aren't scanned at
-- ALTER time. Future inserts/updates ARE checked. To validate later (after
-- a backfill cleans bad rows): `ALTER TABLE x VALIDATE CONSTRAINT name`.

-- ─── Chicago bbox helper (used by location CHECKs) ────
-- Inlining the bbox in every CHECK is verbose and error-prone. Centralize.
CREATE OR REPLACE FUNCTION in_chicago_bbox(g GEOMETRY)
RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE AS $$
  SELECT g IS NULL OR (
    ST_X(g) BETWEEN -87.940 AND -87.524
    AND ST_Y(g) BETWEEN 41.644 AND 42.023
  );
$$;

-- ─── buildings ────────────────────────────────────────
ALTER TABLE buildings
  ADD CONSTRAINT buildings_address_norm_present
    CHECK (address_norm IS NOT NULL) NOT VALID;
ALTER TABLE buildings
  ADD CONSTRAINT buildings_purchase_price_nonneg
    CHECK (purchase_price IS NULL OR purchase_price >= 0) NOT VALID;
ALTER TABLE buildings
  ADD CONSTRAINT buildings_tax_annual_nonneg
    CHECK (tax_annual IS NULL OR tax_annual >= 0) NOT VALID;
ALTER TABLE buildings
  ADD CONSTRAINT buildings_year_built_sane
    CHECK (year_built IS NULL OR year_built BETWEEN 1830 AND 2100) NOT VALID;
ALTER TABLE buildings
  ADD CONSTRAINT buildings_location_in_chicago
    CHECK (in_chicago_bbox(location)) NOT VALID;

-- ─── cpd_incidents ────────────────────────────────────
ALTER TABLE cpd_incidents
  ADD CONSTRAINT cpd_location_in_chicago
    CHECK (in_chicago_bbox(location)) NOT VALID;
-- date already NOT NULL in 001; type already CHECKed in 001.

-- ─── complaints_311 ───────────────────────────────────
ALTER TABLE complaints_311
  ADD CONSTRAINT complaints_311_date_present
    CHECK (date IS NOT NULL) NOT VALID;
ALTER TABLE complaints_311
  ADD CONSTRAINT complaints_311_location_in_chicago
    CHECK (in_chicago_bbox(location)) NOT VALID;

-- ─── tracts ───────────────────────────────────────────
ALTER TABLE tracts
  ADD CONSTRAINT tracts_population_nonneg
    CHECK (population IS NULL OR population >= 0) NOT VALID;
ALTER TABLE tracts
  ADD CONSTRAINT tracts_vacancy_rate_range
    CHECK (vacancy_rate IS NULL OR (vacancy_rate >= 0 AND vacancy_rate <= 1)) NOT VALID;
ALTER TABLE tracts
  ADD CONSTRAINT tracts_owner_pct_range
    CHECK (owner_occupied_pct IS NULL OR (owner_occupied_pct >= 0 AND owner_occupied_pct <= 1)) NOT VALID;
ALTER TABLE tracts
  ADD CONSTRAINT tracts_renter_pct_range
    CHECK (renter_occupied_pct IS NULL OR (renter_occupied_pct >= 0 AND renter_occupied_pct <= 1)) NOT VALID;

-- NOTE: earlier drafts of this migration added constraint blocks for
-- `building_permits` and `parking_lots` "added in 012". Those tables were
-- never created — migration 012 was repurposed to ACS-only column adds —
-- so the ALTER blocks were dead and broke fresh-DB applies. Removed.
-- When either table is actually created, add its constraints in the
-- creating migration, not back here.

-- ─── Advisory lock helper ─────────────────────────────
-- Each fetcher acquires this at run start so two concurrent runs of the
-- same source can't race. Lock is transaction-scoped — released on COMMIT
-- or ROLLBACK. Hash is deterministic so the same source always maps to
-- the same lock id across processes.
CREATE OR REPLACE FUNCTION acquire_source_lock(p_source TEXT)
RETURNS BOOLEAN
LANGUAGE sql AS $$
  SELECT pg_try_advisory_xact_lock(hashtext('chicago_intel.source.' || p_source));
$$;
