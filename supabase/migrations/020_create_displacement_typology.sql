-- Migration 020 — Urban Displacement Project Chicago tract typology
--
-- UDP (UC Berkeley, w/ SPARCC + DePaul IHS as partners) publishes per-tract
-- gentrification/displacement typology in 8 categories. Static reference data
-- — last refresh 2018, no scheduled re-pull. One-shot load via
-- scripts/load_displacement_typology.py. Confidence 6/10 (vintage 2013–2018).
--
-- Joined to a user coordinate via spatial lookup against tracts.geometry.

CREATE TABLE IF NOT EXISTS displacement_typology (
  geoid     TEXT PRIMARY KEY,
  typology  TEXT NOT NULL,
  CONSTRAINT displacement_typology_geoid_11 CHECK (geoid ~ '^[0-9]{11}$')
);

ALTER TABLE displacement_typology ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS anon_select_displacement_typology ON displacement_typology;
CREATE POLICY anon_select_displacement_typology ON displacement_typology
  FOR SELECT TO anon USING (true);

CREATE OR REPLACE FUNCTION displacement_at(lat FLOAT, lng FLOAT)
RETURNS TABLE(geoid TEXT, typology TEXT)
LANGUAGE sql STABLE AS $$
  SELECT t.id, d.typology
  FROM tracts t
  JOIN displacement_typology d ON d.geoid = t.id
  WHERE ST_Contains(t.geometry, ST_MakePoint(lng, lat))
  LIMIT 1;
$$;
