-- Migration 030 — Affordability engine columns
--
-- Adds the inputs + outputs for the per-CCA affordability engine
-- (docs/affordability_engine_spec.md). Idempotent: ADD COLUMN IF NOT EXISTS.
--
-- Grain:
--   tracts — three NEW raw ACS inputs the fetcher writes (transit/autos/poverty).
--            income/vacancy/tenure already exist (migration 012).
--   ccas   — engine outputs + the tract inputs aggregated (pop-weighted) to CCA,
--            so the neighborhood panel can show the H+T breakdown + sub-scores.
--            run_score + vibe_score already exist (migration 001); they are
--            populated by the lifestyle scorer, not added here.

-- ─── tracts: new ACS raw inputs (written by fetch_acs.py) ───
ALTER TABLE tracts
  ADD COLUMN IF NOT EXISTS poverty_rate    NUMERIC(4,3),   -- B17001 below-poverty share
  ADD COLUMN IF NOT EXISTS transit_share   NUMERIC(4,3),   -- B08301 transit-to-work share
  ADD COLUMN IF NOT EXISTS autos_per_hh    NUMERIC(4,2);   -- B25044 vehicles per household

-- ─── ccas: aggregated inputs + engine outputs ───
ALTER TABLE ccas
  -- inputs aggregated from tracts (pop-weighted) for panel transparency
  ADD COLUMN IF NOT EXISTS income_median        INT,
  ADD COLUMN IF NOT EXISTS vacancy_rate         NUMERIC(4,3),
  ADD COLUMN IF NOT EXISTS renter_occupied_pct  NUMERIC(4,3),
  ADD COLUMN IF NOT EXISTS poverty_rate         NUMERIC(4,3),
  ADD COLUMN IF NOT EXISTS transit_share        NUMERIC(4,3),
  ADD COLUMN IF NOT EXISTS autos_per_hh         NUMERIC(4,2),
  -- modeled H+T cost breakdown (our estimate, not HUD's published LAI)
  ADD COLUMN IF NOT EXISTS housing_cost_mo      INT,
  ADD COLUMN IF NOT EXISTS transport_cost_mo    INT,
  -- 0–10 sub-scores + composite
  ADD COLUMN IF NOT EXISTS afford_score         NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS vuln_score           NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS bike_score           NUMERIC(4,2),
  ADD COLUMN IF NOT EXISTS composite_score      NUMERIC(4,2);
