-- Migration 017 — Anon SELECT policies for public-facing tables
--
-- All Chicago.Intel data is public reference (assessor records, CTA stops,
-- pipeline run metadata). The frontend uses the anon key. Without an
-- explicit SELECT policy, RLS returns 0 rows to anon — which is what was
-- happening: service key saw all rows, anon saw none.
--
-- Scope is narrow: only tables the frontend currently reads. Other tables
-- (cpd_incidents, complaints_311, parks, etc.) stay locked until a UI
-- section actually queries them (no-bloat).
--
-- Idempotent: enables RLS only if not already on, drops + recreates each
-- policy by name.

-- buildings ─── frontend: find_building_at RPC
ALTER TABLE buildings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS anon_select_buildings ON buildings;
CREATE POLICY anon_select_buildings ON buildings
  FOR SELECT TO anon USING (true);

-- cta_stops ─── frontend: nearest_cta RPC
ALTER TABLE cta_stops ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS anon_select_cta_stops ON cta_stops;
CREATE POLICY anon_select_cta_stops ON cta_stops
  FOR SELECT TO anon USING (true);

-- pipeline_runs ─── frontend: getLastSyncedAt (freshness UI)
ALTER TABLE pipeline_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS anon_select_pipeline_runs ON pipeline_runs;
CREATE POLICY anon_select_pipeline_runs ON pipeline_runs
  FOR SELECT TO anon USING (true);
