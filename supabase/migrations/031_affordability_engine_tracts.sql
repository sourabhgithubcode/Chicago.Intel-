-- Migration 031 — Affordability engine at TRACT grain
--
-- Extends the per-CCA engine (migration 030) down to census tracts so the map
-- can shade granular within-neighborhood variation. tracts already hold the
-- inputs (rent_median, income_median, poverty_rate, vacancy_rate, transit_share,
-- autos_per_hh from 012+030; safety/walk/disp scores). This adds the engine
-- OUTPUTS, written by the tract paths of scoring/{affordability,vulnerability,
-- lifestyle,composite}.py. Idempotent: ADD COLUMN IF NOT EXISTS.

ALTER TABLE tracts
  ADD COLUMN IF NOT EXISTS housing_cost_mo    INT,
  ADD COLUMN IF NOT EXISTS transport_cost_mo  INT,
  ADD COLUMN IF NOT EXISTS afford_score       NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS vuln_score         NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS vibe_score         NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS bike_score         NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS run_score          NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS composite_score    NUMERIC(4,2);
