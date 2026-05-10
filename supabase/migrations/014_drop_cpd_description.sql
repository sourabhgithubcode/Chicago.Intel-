-- Migration 014 — Drop cpd_incidents.description
--
-- The description column duplicates iucr 1:1 via Chicago's public IUCR
-- lookup table (~400 rows). With 1.47M crime incidents loaded, dropping
-- description recovers ~150MB on Supabase free tier — enough headroom
-- to finish loading the remaining 408K assessor parcels.
--
-- We keep iucr (4 chars) so granular crime labels can be rehydrated on
-- demand via the public lookup.
--
-- Idempotent: IF EXISTS guards re-run.

ALTER TABLE cpd_incidents DROP COLUMN IF EXISTS description;
