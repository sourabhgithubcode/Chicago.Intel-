-- Migration 012 — ACS variable expansion on tracts (§13.22)
--
-- Adds the ACS variable columns now populated by fetch_acs.py.
-- Idempotent: ADD COLUMN IF NOT EXISTS.

ALTER TABLE tracts
  ADD COLUMN IF NOT EXISTS income_median        INT,
  ADD COLUMN IF NOT EXISTS income_moe           INT,
  ADD COLUMN IF NOT EXISTS vacancy_rate         NUMERIC(4,3),
  ADD COLUMN IF NOT EXISTS owner_occupied_pct   NUMERIC(4,3),
  ADD COLUMN IF NOT EXISTS renter_occupied_pct  NUMERIC(4,3);
