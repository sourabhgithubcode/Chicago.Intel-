-- Tracks four cache tables that were created directly in Supabase
-- without a migration file. IF NOT EXISTS makes this safe to re-apply.

-- ── noise_cache ──────────────────────────────────────────────────────────────
-- HowLoud soundscore per coordinate. 1yr TTL (noise is static).

CREATE TABLE IF NOT EXISTS noise_cache (
  coord_key   text                     NOT NULL,
  lat         double precision         NOT NULL,
  lng         double precision         NOT NULL,
  score       integer                  NOT NULL,
  components  jsonb,
  fetched_at  timestamptz              NOT NULL DEFAULT now(),
  row_hash    text                     NOT NULL,
  run_id      text,
  PRIMARY KEY (coord_key)
);

CREATE INDEX IF NOT EXISTS idx_noise_fetched_at ON noise_cache (fetched_at);

-- ── commute_cache ────────────────────────────────────────────────────────────
-- Google Maps travel time per building + work destination + mode.

CREATE TABLE IF NOT EXISTS commute_cache (
  building_pin  text             NOT NULL,
  work_lat      double precision NOT NULL,
  work_lng      double precision NOT NULL,
  mode          text             NOT NULL,
  minutes       integer          NOT NULL,
  distance_m    integer,
  fetched_at    timestamptz      NOT NULL DEFAULT now(),
  row_hash      text             NOT NULL,
  run_id        text,
  PRIMARY KEY (building_pin, work_lat, work_lng, mode)
);

CREATE INDEX IF NOT EXISTS idx_commute_pin       ON commute_cache (building_pin);
CREATE INDEX IF NOT EXISTS idx_commute_fetched_at ON commute_cache (fetched_at);

-- ── aqi_cache ────────────────────────────────────────────────────────────────
-- EPA AirNow AQI per ZIP code. Short TTL — refreshed daily.

CREATE TABLE IF NOT EXISTS aqi_cache (
  zip                 text        NOT NULL,
  aqi                 integer     NOT NULL,
  primary_pollutant   text,
  category            text,
  source_observed_at  timestamptz,
  fetched_at          timestamptz NOT NULL DEFAULT now(),
  row_hash            text        NOT NULL,
  run_id              text,
  PRIMARY KEY (zip)
);

CREATE INDEX IF NOT EXISTS idx_aqi_fetched_at ON aqi_cache (fetched_at);

-- ── address_suggestions_cache ────────────────────────────────────────────────
-- Google Places Autocomplete results per normalized query string. 30d TTL.

CREATE TABLE IF NOT EXISTS address_suggestions_cache (
  query_norm     text        NOT NULL,
  results        jsonb       NOT NULL,
  session_token  text,
  fetched_at     timestamptz NOT NULL DEFAULT now(),
  row_hash       text        NOT NULL,
  run_id         text,
  PRIMARY KEY (query_norm)
);

CREATE INDEX IF NOT EXISTS idx_address_suggestions_fetched_at
  ON address_suggestions_cache (fetched_at);
