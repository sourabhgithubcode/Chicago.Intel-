-- Migration 019 — RentCast per-PIN rent estimate cache
--
-- RentCast is paid per-call. Aggressive caching is the cost lever — same
-- PIN re-quotes once per 30d at most. Bedroom count is part of the key
-- since rent varies sharply by unit size.

CREATE TABLE IF NOT EXISTS rent_cache (
  pin           TEXT NOT NULL,
  bedrooms      INT NOT NULL,
  rent          INT,
  rent_low      INT,
  rent_high     INT,
  comparables   JSONB,
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (pin, bedrooms),
  CONSTRAINT rent_cache_pin_14digits CHECK (pin ~ '^[0-9]{14}$'),
  CONSTRAINT rent_cache_bedrooms_sane CHECK (bedrooms BETWEEN 0 AND 10)
);

ALTER TABLE rent_cache ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS anon_select_rent_cache ON rent_cache;
CREATE POLICY anon_select_rent_cache ON rent_cache
  FOR SELECT TO anon USING (true);
