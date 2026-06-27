-- Migration 026 — Anon SELECT policies for ccas + tracts
--
-- RLS is enabled on ccas and tracts but migration 017 only added anon policies
-- for buildings / cta_stops / pipeline_runs. With RLS on and no policy, the anon
-- key (which the frontend uses) gets 0 rows — so for real users the CCA card
-- (getCcaById → ccas), the breadcrumb (cca_containing_point / tract_containing_point),
-- DisplacementRisk (displacement_at joins tracts), and the map CCA/tract polygons
-- (cca_geojson / tract_geojson, SECURITY INVOKER) all come back empty. The service
-- key bypasses RLS, which is why this was invisible in admin checks.
--
-- These tables hold only public reference data (neighborhood boundaries + scores),
-- so anon read is appropriate.

ALTER TABLE ccas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS anon_select_ccas ON ccas;
CREATE POLICY anon_select_ccas ON ccas
  FOR SELECT TO anon USING (true);

ALTER TABLE tracts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS anon_select_tracts ON tracts;
CREATE POLICY anon_select_tracts ON tracts
  FOR SELECT TO anon USING (true);
