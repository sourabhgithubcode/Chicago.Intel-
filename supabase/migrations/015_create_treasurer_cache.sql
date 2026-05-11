-- Migration 015 — Treasurer per-PIN cache
--
-- Cook County Treasurer publishes no API. The treasurer-lookup Edge Function
-- scrapes taxbillhistorysearch.aspx → setsearchparameters.aspx →
-- yourpropertytaxoverviewresults.aspx per PIN and persists the result here so
-- we don't re-scrape on every page view. TTL is enforced in the function
-- (currently 30d); rows are kept as a debug trail beyond that.

CREATE TABLE IF NOT EXISTS treasurer_cache (
  pin           TEXT PRIMARY KEY,
  tax_year      INT,
  total_billed  NUMERIC(12,2),
  total_paid    NUMERIC(12,2),
  amount_due    NUMERIC(12,2),
  raw_text      TEXT,
  fetched_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT treasurer_cache_pin_14digits
    CHECK (pin ~ '^[0-9]{14}$')
);
