# Chicago.Intel — Data Dictionary

> **Single source of truth for: which variable lives at which layer, where it comes from, how it joins to everything else, and what confidence we attach to it.**
>
> This document is the spec the rest of the codebase implements. When the dictionary and the code disagree, the dictionary is wrong — fix the dictionary, then fix the code. Update this file in the same PR as any data-pipeline or schema change.

**Status legend:** ✅ shipped · 🟨 partial / scaffolded · 🟥 stub / not started · ⚪ deferred / V3+

---

## Section 1 — The 4-Layer Model

| # | Layer | Table | Primary Key | Row Count | Geometry |
|---|-------|-------|-------------|-----------|----------|
| 1 | CCA (Neighborhood) | `ccas` | `id` INT | 77 | MULTIPOLYGON 4326 |
| 2 | Tract | `tracts` | `id` TEXT (Census GEOID) | ~800 | MULTIPOLYGON 4326 |
| 3 | **Street** (new — see §2) | `streets` | `id` TEXT | ~50K segments | LINESTRING 4326 |
| 4 | Building | `buildings` | `pin` TEXT (Cook County PIN) | ~1.9M | POINT 4326 |

**No City layer.** Chicago-wide aggregates, when shown, are computed inline as `SUM/AVG over all CCAs`. They are never persisted to a table.

### 1.1 Storage pattern — medallion (bronze → silver → gold)

| Layer | What it holds | Where it lives | Read by |
|-------|---------------|----------------|---------|
| **Bronze** | raw API responses, gzipped JSONL, append-only (audit/replay) | `data/bronze/{source}/{run_id}.jsonl.gz` (local) or R2 bucket | pipeline only — **never frontend** |
| **Silver** | per-source normalized Postgres tables | Supabase tables (`buildings`, `tracts`, `cpd_incidents`, `cta_stops`, `complaints_311`, `parks`, `streets` (new)) | pipeline + admin tooling |
| **Gold** | denormalized materialized views, joins pre-computed | Supabase MVs: `gold_address_intel`, `gold_street_summary` (new), `gold_tract_summary`, `gold_cca_summary` | **frontend reads ONLY here** |

Bronze writer: `scripts/utils/bronze_store.py`. Gold definitions: `supabase/migrations/006_gold_materialized_views.sql`. Refresh helper: `refresh_gold_layer()` PL/pgSQL function (called at end of every pipeline run via the orchestrator).

### 1.2 Does each API have exactly one table?

**Short answer: no, not strictly.** Most APIs own one table; a few share or enrich; live-only APIs don't get a table at all.

| API | Has a silver landing? | Which one | Trigger | Notes |
|-----|------------------------|-----------|---------|-------|
| Cook County Assessor | yes | `buildings` (creates rows) | batch | canonical building identity (PIN) |
| Cook County Treasurer | shares with Assessor | `buildings` (enriches `tax_current`, `tax_annual`) | batch | NO new rows — same building entity |
| ACS (Census API) | yes | `tracts` | batch | CCA rent rolls up from tracts in gold step |
| CPD (Chicago Data Portal) | yes | `cpd_incidents` | batch | one row per incident |
| 311 (Chicago Data Portal) | yes | `complaints_311` | batch | one row per complaint |
| CTA GTFS | yes | `cta_stops` | batch | one row per stop |
| Chicago Park District | yes | `parks` | batch | one row per park |
| Chicago Street Centerlines | yes | `streets` (new — §2) | batch | one row per segment |
| Google Places | shares with Yelp | `amenities_cache` (`source = 'google'`) | **lazy-on-view** (ToS forbids bulk pre-cache) | 30-day TTL |
| Yelp | shares with Places | `amenities_cache` (`source = 'yelp'`) | lazy-on-view | 30-day TTL |
| Google Maps Geocoding | yes (column) | `buildings.location` (cached forever once geocoded) + `geocodeCache` LRU 24h for in-flight typeahead | lazy-on-view | client cache is a perf shim only — silver is canonical |
| FEMA NFHL | yes (column) | enriches `buildings.flood_zone` + `flood_zone_at` | lazy-on-view, 1yr TTL | one value per building |
| Illinois Report Card | yes (column) | enriches `buildings.school_elem`, `buildings.school_rating`, `school_rating_at` | annual batch | RCDT lookup |
| AirNow | yes (new — `010`) | `aqi_cache(zip, aqi, primary_pollutant, fetched_at)` | lazy-on-view, 1h TTL | hourly source |
| HowLoud | yes (new — `010`) | `noise_cache(coord_key, score, fetched_at)` | lazy-on-view, 1yr TTL | one score per coord |
| Rentcast | yes (column — `010`) | `buildings.rent_estimate`, `buildings.rent_estimate_at`; user override always wins | lazy-on-view, 30d TTL | quoted as estimate, never authoritative |
| Mapbox Routing (commute) | yes (new — `010`) | `commute_cache(building_pin, work_lat, work_lng, mode, minutes, fetched_at)` | lazy-on-request, 30d TTL | OD-pair specific; can't pre-cache, but second user pays nothing |
| Mapbox Geocoding | yes (column) | falls back to writing `buildings.location` like Google Maps Geocoding | lazy-on-view | only used as fallback to Google |
| SpotHero | no table | replaced by Chicago Data Portal parking dataset | n/a | partnership-blocked |
| Supabase | n/a (it IS the DB) | — | n/a | RPC layer |

Tally (post-`010`): 19 of 20 external sources land in silver (8 batch, 9 lazy-on-view, 2 column-only). Only SpotHero is excluded, because we no longer use it.

**Why the deviations:** Treasurer + Assessor describe the same physical entity (a PIN); Places + Yelp answer the same question ("what's within 0.25mi?") and merging cuts a UNION; per-coord live signals (FEMA, HowLoud, AirNow) live as a column or a tiny key→value cache instead of a full table because they produce one value per key.

**Default for any new source:** one fetcher → one transformer → one new entry in `scripts/loaders/__init__.py::SILVER_TABLE` → one new silver table. Deviating requires a one-line justification recorded here.

### 1.3 Frontend never joins — gold is the contract

| User action | Query | Joins at query time? |
|-------------|-------|----------------------|
| Building search | `SELECT * FROM gold_address_intel WHERE pin = ?` | None — pre-joined |
| Tract / CCA / Street panel | `SELECT * FROM gold_*_summary WHERE id = ?` | None |
| Map polygons | `SELECT id, geometry, color_metric FROM gold_*_summary` | None |
| 7-dim comparison (§9.7) | two single-row reads (anchor + candidate); deltas in JS | None |
| Free-coord click on map | RPC `safety_at_point(lat, lng)`, `nearest_cta(lat, lng)` | **Yes** — single GIST-indexed spatial query, single-digit ms |

All spatial / text / KNN joins happen **once per pipeline run** during reconcile + gold refresh (§10.3). After the run, gold rows hold the join results as plain columns.

Trade-off: gold materialization duplicates ~1 GB of data and forces Supabase Pro ($25/mo). Benefit: every page is a single-row read; latency does not grow with dataset size. The dictionary's job is to keep this duplication safe by pinning the join rules so gold-refresh SQL stays unambiguous.

### 1.4 The medallion contract (hard + soft rules)

This section pins the principle so it doesn't get re-litigated in PR review.

**Hard rule — frontend reads only from gold.**
The frontend never holds a value the user sees that did not first land in bronze → silver → gold. The set of files allowed to make outbound API calls from the browser is exactly: `src/lib/api/supabase.js` (queries gold MVs / RPCs), and *nothing else*. The other `src/lib/api/*.js` files are wrappers that issue calls on behalf of the lazy fetchers; their results are written to silver before being returned to React state.

**Soft rule — every external source persists.**
Even on-demand sources (FEMA, Places, Yelp, HowLoud, AirNow, Rentcast, Mapbox routing) write their result to a silver table the first time we fetch it. The next time the same key is requested — even by a different user, even months later — we serve from silver. Client-side LRU caches still exist as a per-session perf shim, but silver is canonical: clearing the LRU never costs the second user anything they already paid for.

**Two genuine exceptions** (codified, not hidden):
1. **Google Places ToS.** Bulk pre-caching `place_id` data is forbidden. Stays lazy-on-view, never crawled. Caching the response of a user-triggered request for 30 days is permitted and is what we do.
2. **Mapbox routing.** Pre-caching is impossible because the OD pair depends on the user's work pin. But the response *is* persisted (`commute_cache`), so a second user with the same OD pair pays nothing.

**What this forbids:**
- A React component calling `fetch('https://api.howloud.com/...')` directly and showing the result without writing to `noise_cache`.
- A `src/lib/api/*.js` returning an LRU value the user sees that has no silver landing.
- A "client-side LRU only" entry in §6.2 — every row in §6.2 must name a silver landing or be excluded.

**Enforcement:**
- `eslint-plugin-no-direct-api-call` (custom rule, to add) flags any `fetch`/`axios` call outside `src/lib/api/`.
- Silver-write contract enforced inside each `src/lib/api/{source}.js` wrapper: function returns only after the silver upsert resolves.
- Verification step #10 (added to bottom of doc) — every `src/lib/api/*.js` wrapper has a corresponding silver landing in §1.2.

---

## Section 2 — New Street Layer (Spec for migration `007_create_streets.sql`)

The streets layer doesn't exist yet. This section is the spec a follow-up migration must implement.

- **Source:** Chicago Data Portal — *Street Center Lines* dataset, Socrata id `6imu-meau` (free, no key).
- **Granularity:** one row per centerline segment (block-level).
- **Refresh:** annual (rarely changes).
- **Confidence:** 9/10 (official city centerline data).

### Schema (proposed)

```sql
CREATE TABLE streets (
  id            TEXT PRIMARY KEY,           -- street_id from source
  name          TEXT NOT NULL,              -- "N Lincoln Ave"
  name_norm     TEXT,                       -- normalized for joins
  from_addr     INT,                        -- low end of address range
  to_addr       INT,                        -- high end
  cca_id        INT REFERENCES ccas(id),    -- spatial assignment
  tract_id      TEXT REFERENCES tracts(id), -- spatial assignment
  geometry      GEOMETRY(LINESTRING, 4326)
);
CREATE INDEX ON streets USING GIST(geometry);
CREATE INDEX ON streets(name_norm);

ALTER TABLE buildings
  ADD COLUMN street_id TEXT REFERENCES streets(id);
CREATE INDEX ON buildings(street_id);
```

### Spatial assignment job

After streets load, before gold refresh:
```sql
UPDATE buildings b
   SET street_id = (
       SELECT s.id
         FROM streets s
        WHERE ST_DWithin(b.location, s.geometry, 30)
        ORDER BY s.geometry <-> b.location
        LIMIT 1
   );
```

### gold_street_summary (proposed)

One row per segment, pre-joined with the same shape pattern as `gold_address_intel`:
- `id`, `name`, `from_addr`, `to_addr`, `geometry`
- `cca_id`, `tract_id` (passthrough)
- `building_count`, `avg_landlord_score` (from contained `buildings`)
- `violent_5yr`, `complaints_311_5yr` (within 100m buffer of segment)
- `flood_zone_modal` (most-common flood zone among contained buildings)
- `grocery_tier_modal`, `dining_tier_modal` (modal Google `price_level` within 0.25mi)
- `nearest_cta_name`, `nearest_cta_m` (KNN from segment centroid)

---

## Section 2.5 — Lazy-cache silver tables (Spec for migration `010_lazy_cache_tables.sql`)

§1.4 promotes every external source to a silver landing. The batch sources already have tables (§1.2). This section is the spec for the lazy-on-view sources that don't yet — one migration, four small tables + five column adds.

### New tables

```sql
-- AirNow AQI by ZIP, hourly TTL
CREATE TABLE aqi_cache (
  zip                TEXT PRIMARY KEY,
  aqi                INT NOT NULL,
  primary_pollutant  TEXT,
  category           TEXT,                          -- "Good" / "Moderate" / etc.
  source_observed_at TIMESTAMPTZ,                   -- AirNow's reported observation time
  fetched_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  row_hash           TEXT NOT NULL,
  run_id             TEXT                           -- matches pipeline_runs.run_id (TEXT) in 005
);

-- HowLoud noise score by coordinate, 1yr TTL
CREATE TABLE noise_cache (
  coord_key          TEXT PRIMARY KEY,              -- "lat:41.87810|lng:-87.62980" (5dp rounded)
  lat                DOUBLE PRECISION NOT NULL,
  lng                DOUBLE PRECISION NOT NULL,
  score              INT NOT NULL,                  -- 0–100 HowLoud
  components         JSONB,                         -- traffic / nightlife / etc. sub-scores
  fetched_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  row_hash           TEXT NOT NULL,
  run_id             TEXT
);

-- Mapbox routing by OD pair, 30d TTL
CREATE TABLE commute_cache (
  building_pin       TEXT NOT NULL REFERENCES buildings(pin) ON DELETE CASCADE,
  work_lat           DOUBLE PRECISION NOT NULL,
  work_lng           DOUBLE PRECISION NOT NULL,
  mode               TEXT NOT NULL,                 -- 'driving' | 'transit' | 'walking' | 'cycling'
  minutes            INT NOT NULL,
  distance_m         INT,
  fetched_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  row_hash           TEXT NOT NULL,
  run_id             TEXT,
  PRIMARY KEY (building_pin, work_lat, work_lng, mode)
);

-- Google Places Autocomplete suggestions, 24h TTL
CREATE TABLE address_suggestions_cache (
  query_norm         TEXT PRIMARY KEY,              -- lowercased trimmed query
  results            JSONB NOT NULL,                -- [{place_id, description, structured_formatting}, ...]
  session_token      TEXT,                          -- Places New session billing token
  fetched_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  row_hash           TEXT NOT NULL,
  run_id             TEXT
);
```

### New columns on `buildings`

```sql
ALTER TABLE buildings
  ADD COLUMN flood_zone_at      TIMESTAMPTZ,        -- when FEMA was last fetched (1yr TTL)
  ADD COLUMN rent_estimate      NUMERIC,            -- Rentcast monthly $; user override always wins
  ADD COLUMN rent_estimate_at   TIMESTAMPTZ,        -- when Rentcast was last fetched (30d TTL)
  ADD COLUMN school_rating      TEXT,               -- IL Report Card letter / score
  ADD COLUMN school_rating_at   TIMESTAMPTZ;        -- annual TTL
```

### TTL refresh rule (shared by every wrapper)

```text
fresh = NOW() - fetched_at < TTL
fresh ? serve from silver : refetch → upsert → return
```
The wrapper never returns to React state until the silver upsert resolves.

### Coord rounding for `noise_cache.coord_key`

5 decimal places ≈ 1.1m precision. Two requests for the same lat/lng-rounded address share a row. This avoids cache fragmentation from floating-point noise.

### Why these are silver, not gold

These rows are per-key, not per-entity rollups. Gold MVs read from them when refreshing `gold_address_intel` (e.g. `flood_zone`, `school_rating` get pulled forward); the lazy-cache tables themselves are silver — directly readable by the wrapper, not by the frontend.

### Frontend never reads these directly

Per §1.4, the frontend only reads gold. When a user views a building, gold has the values already pulled forward. When a wrapper triggers a fresh fetch (cache miss / stale TTL), the wrapper writes silver and the next gold refresh pulls it forward — but the user-visible value comes from `gold_address_intel` regardless. For values that miss the gold refresh window (a fresh FEMA fetch right now), the wrapper returns the silver row directly to gold-shaped React state via a single-row read; gold's role is the single contract, not the only path.

---

## Section 3 — Variable × Layer Matrix

The core of the dictionary. Each row = one (variable, layer) pair with the rule used.

**Rule legend:**
- `passthrough` — value is stored on this layer's row directly
- `pop-weighted` — weighted average using `tracts.population` weights
- `spatial-sum` — sum of point/polygon counts inside parent geometry
- `spatial-buffer` — sum within an explicit distance buffer
- `KNN` — nearest-neighbor (single result) via GIST index
- `aggregate` — `COUNT/AVG/SUM` of contained children
- `N/A` — variable does not apply at this layer

### 3.1 Identity & geography

| Variable | Native | CCA | Tract | Street | Building | Source | Confidence |
|----------|--------|-----|-------|--------|----------|--------|-----------|
| Name / label | per layer | `ccas.name` | `tracts.name` | `streets.name` | `buildings.address` | various | 10/10 |
| Geometry | per layer | `ccas.geometry` MULTIPOLYGON | `tracts.geometry` MULTIPOLYGON | `streets.geometry` LINESTRING | `buildings.location` POINT | various | 9–10/10 |
| Containing CCA | n/a | self | `tracts.cca_id` FK | `streets.cca_id` (spatial assigned) | derived via `ST_Contains` in gold | derived | 10/10 |
| Containing tract | n/a | n/a | self | `streets.tract_id` (spatial assigned) | derived via `ST_Contains` in gold | derived | 10/10 |
| Containing street | n/a | n/a | n/a | self | `buildings.street_id` (KNN within 30m) | derived | 9/10 |

### 3.2 Cost / financial

| Variable | Native | CCA | Tract | Street | Building | Source | Confidence |
|----------|--------|-----|-------|--------|----------|--------|-----------|
| Median rent | Tract (ACS B25064) | `pop-weighted` of contained tracts → `ccas.rent_median` | `passthrough` `tracts.rent_median` | passthrough from containing tract | passthrough from containing tract | ACS API | 8/10 (CCA), 6/10 (tract) |
| Rent margin of error | Tract | not stored | `passthrough` `tracts.rent_moe` | n/a | n/a | ACS B25003 | 6/10 |
| User-entered rent | Building | n/a | n/a | n/a | UI input override | user | 9/10 |
| Take-home pay | computed | n/a | n/a | n/a | `taxEngine.calculate(salary)` (live) | IRS 2024 + IL DOR + FICA | 10/10 |
| Owner | PIN (Assessor) | n/a | n/a | n/a | `passthrough` `buildings.owner` | Assessor | 9/10 |
| Year built | PIN (Assessor) | n/a | n/a | n/a | `passthrough` `buildings.year_built` | Assessor | 9/10 |
| Purchase year + price | PIN (Assessor) | n/a | n/a | n/a | `passthrough` `buildings.purchase_year` / `purchase_price` | Assessor | 9/10 |
| Tax current | PIN (Treasurer) | n/a | n/a | n/a | `passthrough` `buildings.tax_current` | Treasurer | 9/10 |
| Tax annual | PIN (Treasurer) | n/a | n/a | n/a | `passthrough` `buildings.tax_annual` | Treasurer | 9/10 |
| Delinquent buildings | derived | `aggregate` `gold_cca_summary.delinquent_buildings` | n/a | n/a | per-row `tax_current=false` | gold view | 9/10 |
| Grocery price tier | Place (Google) | n/a | n/a | modal within 0.25mi | modal within 0.25mi | `amenities_cache` | 7/10 (signal) |
| Dining price tier | Place (Google) | n/a | n/a | modal within 0.25mi | modal within 0.25mi | `amenities_cache` | 7/10 (signal) |
| Parking delta | per-spot | n/a | n/a | spot density / segment | nearest paid garage rate − free street | SpotHero / Chicago Data Portal | 7/10 |
| Healthcare OOP | user-adjustable | n/a | n/a | n/a | slider (default MIT Living Wage) | MIT | 8/10 |

### 3.3 Safety / risk

| Variable | Native | CCA | Tract | Street | Building | Source | Confidence |
|----------|--------|-----|-------|--------|----------|--------|-----------|
| Violent crime (5yr) | Point (CPD) | `spatial-sum` `ST_Contains(ccas.geometry, location)` | `spatial-sum` (tract) | `spatial-buffer` 100m | `spatial-buffer` 402m (0.25mi) → `gold_address_intel.violent_5yr` | `cpd_incidents` | 7/10 |
| Property crime (5yr) | Point (CPD) | `spatial-sum` | `spatial-sum` | `spatial-buffer` 100m | `spatial-buffer` 402m → `gold_address_intel.property_5yr` | `cpd_incidents` | 7/10 |
| Violent crime (1yr, current) | Point (CPD) | `gold_cca_summary.violent_1yr` | not stored | not stored | not stored | `cpd_incidents` | 7/10 |
| Crime trend slope (3yr) | derived | derived from yearly counts | derived | derived | derived | `cpd_incidents` | 7/10 |
| Flood zone | Coord (FEMA live) | n/a | n/a | `flood_zone_modal` of contained buildings | `passthrough` `buildings.flood_zone` (cached on first lookup) | FEMA NFHL | 9/10 |
| Building violations (5yr) | Point + address (311) | n/a | `spatial-sum` | `spatial-buffer` 100m | `passthrough` `buildings.violations_5yr` (text + spatial join) | `complaints_311` | 9/10 |
| Heat complaints | Point + address (311) | n/a | n/a | `spatial-buffer` 100m | `passthrough` `buildings.heat_complaints` | `complaints_311` | 9/10 |
| Bed bug reports | Point + address (311) | n/a | n/a | `spatial-buffer` 100m | `passthrough` `buildings.bug_reports` | `complaints_311` | 9/10 |
| Displacement risk | Tract (DePaul IHS) | `pop-weighted` from tracts | `passthrough` `tracts.disp_score` | passthrough from tract | passthrough from tract | DePaul IHS + ACS | 7/10 |

### 3.4 Livability

| Variable | Native | CCA | Tract | Street | Building | Source | Confidence |
|----------|--------|-----|-------|--------|----------|--------|-----------|
| Walk score | per-coord | `passthrough` `ccas.walk_score` | `passthrough` `tracts.walk_score` | derived along segment | per-address (Walk Score API or amenity-density proxy) | Walk Score / proxy | 7/10 |
| Vibe score (Yelp) | per-coord | `passthrough` `ccas.vibe_score` | n/a | n/a | per-address (live) | Yelp Fusion | 6/10 (N. Side bias) |
| Noise score | per-coord (HowLoud) | n/a | n/a | n/a | live, client-cached | HowLoud | 7/10 |
| Run score | per-coord | `passthrough` `ccas.run_score` | n/a | n/a | n/a | Strava heatmap proxy | 6/10 |
| Nearest CTA stop | Point (GTFS) | n/a | n/a | KNN from segment centroid | `KNN` → `gold_address_intel.nearest_cta_name`, `nearest_cta_m`, `nearest_cta_lines` | `cta_stops` | 9/10 |
| Nearest park | Point (Park District) | n/a | n/a | KNN from segment centroid | `KNN` → `gold_address_intel.nearest_park_name`, `nearest_park_m`, `nearest_park_acreage` | `parks` | 9/10 |
| Park acreage within 0.5mi | derived | `spatial-sum` | `spatial-sum` | `spatial-buffer` | `spatial-buffer` | `parks.acreage` × `boundary` | 9/10 |
| Amenity density (16 cats) | Place (Google) | n/a | n/a | count within 0.25mi | count within 0.25mi → cache | `amenities_cache` | 7/10 (signal) |
| AQI | per-zip (AirNow) | n/a | n/a | n/a | live, client-cached | AirNow | 7/10 |

### 3.5 Building quality

| Variable | Native | CCA | Tract | Street | Building | Source | Confidence |
|----------|--------|-----|-------|--------|----------|--------|-----------|
| Landlord score | derived per building | `aggregate` `AVG` from gold_cca_summary | `aggregate` `AVG` from gold_tract_summary | `aggregate` `AVG` from gold_street_summary | `passthrough` `buildings.landlord_score` (computed in reconcile) | composite | 7/10 |
| Building count | derived | `gold_cca_summary.building_count` | `gold_tract_summary.building_count` | `gold_street_summary.building_count` (new) | n/a | gold view | 9/10 |
| Owner-occupied heuristic | derived per PIN | n/a | n/a | n/a | `buildings.owner` matches `buildings.address_norm` | derived | 6/10 |
| School (elementary) | per-coord | n/a | n/a | n/a | `passthrough` `buildings.school_elem` (CPS attendance boundary) | CPS + IL Report Card | 7/10 |

### 3.6 Composite (per-building canonical)

| Variable | Native | CCA | Tract | Street | Building | Source | Confidence |
|----------|--------|-----|-------|--------|----------|--------|-----------|
| Financial Reality Index (40%) | per-building | `aggregate` `AVG` of contained | `aggregate` `AVG` | `aggregate` `AVG` | `passthrough` (canonical) | derived (lib/calculations) | per components |
| Livability Index (30%) | per-building | `aggregate` `AVG` | `aggregate` `AVG` | `aggregate` `AVG` | `passthrough` (canonical) | derived | per components |
| Stability Index (20%) | per-building | `aggregate` `AVG` | `aggregate` `AVG` | `aggregate` `AVG` | `passthrough` (canonical) | derived | per components |
| Opportunity Index (10%) | per-building | `aggregate` `AVG` | `aggregate` `AVG` | `aggregate` `AVG` | `passthrough` (canonical) | derived | per components |
| Composite address score | derived | `AVG` of building composites in CCA | `AVG` (tract) | `AVG` (street) | `Σ weighted indices` (canonical) | derived | per components |

Building is the canonical home. Higher-layer composites are aggregates and **must carry the caveat** *"Aggregate of N buildings — drill into a tract or street for the underlying values."*

### 3.7 Distribution-aware aggregation (anti-median rule)

A median (or mean, or modal) is one number. Two polygons with identical medians can hide opposite realities — flat vs wide spread. To prevent the user from making decisions on a number that hides its own variance, **every aggregated metric must also carry its spread**.

#### Required companion fields

For any column that ends in `_median`, `_avg`, `_modal`, or is otherwise a central-tendency aggregate, add these companions in the same gold MV row:

| Companion | What it answers | Computed by |
|-----------|------------------|-------------|
| `_min` | "what's the cheapest / safest / lowest?" | `MIN(child.value)` |
| `_max` | "what's the most expensive / worst / highest?" | `MAX(child.value)` |
| `_p25` | "the bottom 25% are at or below ___" | `percentile_cont(0.25) WITHIN GROUP (ORDER BY child.value)` |
| `_p75` | "the top 25% are at or above ___" | `percentile_cont(0.75) WITHIN GROUP (ORDER BY child.value)` |
| `_count` | "how many children went into this number?" | `COUNT(child.value)` (excludes NULLs) |

For modal categorical aggregates (price tier, flood zone), replace `_p25/_p75` with `_distribution JSONB` — a tiny histogram like `{"$": 12, "$$": 47, "$$$": 18, "$$$$": 3}`.

#### Concrete examples

| Today | Today + distribution |
|-------|----------------------|
| `tracts.rent_median = 1387` | `+ rent_min = 825, rent_max = 2940, rent_p25 = 1100, rent_p75 = 1690, rent_count = 412` |
| `gold_cca_summary.avg_landlord_score = 7.2` | `+ min_landlord_score = 3.1, max_landlord_score = 9.8, p25 = 6.0, p75 = 8.5, count = 1240` |
| `gold_street_summary.violent_5yr = 12` | `+ violent_5yr_per_block_max = 7, violent_5yr_per_block_p75 = 3, hotspot_count = 2` (blocks with >5) |
| `gold_cca_summary.grocery_tier_modal = 2` | `+ grocery_tier_distribution = {"1": 8, "2": 23, "3": 11, "4": 2}` |

#### Where this lives

Companion fields go in the same gold MV as the central tendency — `gold_address_intel`, `gold_street_summary`, `gold_tract_summary`, `gold_cca_summary`. Same refresh cycle, same single-row read from the frontend. No new tables.

#### Why this matters for "are we recommending right?"

Without the spread, a polygon's color on the map (any color-by metric in §9.4) is a lie about variability. With it, the viewport top-N can show "$1,800 median · $800–$3,200 range · 412 buildings" so a user with a $1,400 budget knows to drill in even though the median exceeds it — and conversely, doesn't get fooled by a tight $1,750–$1,850 polygon that has nothing under $1,750.

The user's "do I match this place?" question can't be answered by the median alone. It's answered by the spread relative to the user's inputs. That's why these companions aren't optional.

---

## Section 4 — Join Key Reference

| Key | Type | Tables that carry it | Used to join |
|-----|------|----------------------|--------------|
| `pin` | TEXT | `buildings` | Assessor + Treasurer (direct) |
| `cca_id` | INT | `ccas`, `tracts` (FK), `streets` (proposed FK), `gold_address_intel`, `gold_tract_summary` | rolling tract / street up to CCA |
| `tract_id` (Census GEOID) | TEXT | `tracts`, `streets` (proposed FK), `gold_address_intel` | rolling building → tract |
| `street_id` (proposed) | TEXT | `streets`, `buildings` (proposed FK), `gold_address_intel` | aggregating buildings to street |
| `address_norm` | TEXT | `buildings`, `complaints_311`, `amenities_cache` (`address_key`) | matching 311 + Places to building |
| `location` | GEOMETRY POINT 4326 | `buildings`, `cpd_incidents`, `complaints_311`, `cta_stops`, `parks`, `amenities_cache` | all spatial joins (`ST_Contains`, `ST_DWithin`, `<->`) |
| `geometry` | GEOMETRY MULTIPOLYGON / LINESTRING | `ccas`, `tracts`, `parks` (`boundary`), `streets` (proposed) | containment / proximity |

**Address normalization** (used everywhere `address_norm` appears) — single helper `lib/utils/normalizeAddress.js` (to add). Steps:
1. Lowercase, trim.
2. Collapse whitespace.
3. Strip directional variations: `North` → `N`, `South` → `S`, `East` → `E`, `West` → `W`.
4. Strip suffix variations: `Street` → `St`, `Avenue` → `Ave`, `Boulevard` → `Blvd`, `Drive` → `Dr`, `Place` → `Pl`, `Court` → `Ct`, `Parkway` → `Pkwy`.
5. Drop apartment / unit suffix into a separate `unit` field.

Stored on `buildings.address_norm`, `complaints_311.address_norm`, `amenities_cache.address_key`. Migrations 001 + 005 already created the columns; the silver loaders must populate them via this helper.

---

## Section 5 — Aggregation Rules (pinned decisions)

Stated once so they don't drift.

- **CCA is the top of the hierarchy.** Chicago-wide totals, when shown, are computed inline (`SUM` over all CCAs) and never persisted. No City table.
- **Tract → CCA rent:** **population-weighted average** using `tracts.population` weights. Reason: simple averages distort small-population tracts.
- **Building → tract / CCA / street: spatial containment** via `ST_Contains(parent.geometry, building.location)`. For `buildings.street_id`, fall back to KNN within 30m if no segment contains the point (LINESTRING containment is rarely exact).
- **Crime point → polygon:** `ST_Contains(parent.geometry, incident.location)`. For Building, use `ST_DWithin(..., 402)` (0.25mi).
- **Crime point → street:** `ST_DWithin(streets.geometry, incident.location, 100)` — 100m buffer covers both sides + half-block.
- **Building → 311:** primary `address_norm` ILIKE; fallback `ST_DWithin(buildings.location, complaint.location, 100)` if no text match. **Both must agree** for confidence band 9/10; either alone → 7/10.
- **Building → nearest amenity / CTA / park:** `ORDER BY location <-> point LIMIT 1` (KNN via GIST).
- **Building → flood zone:** lazy live query to FEMA NFHL on first view; cache to `buildings.flood_zone`.
- **Price tier → cost delta:** **never converted to dollars.** Rendered as $/$$/$$$/$$$$ signal with the `signal, not precise amount` caveat.
- **Population weights for any "average":** if the source variable is a per-population statistic (rent, income, displacement), use `tracts.population` weights. If it's a per-building / per-incident count, use simple `AVG` or `COUNT`.

### 5.1 Reference point per layer for KNN ("nearest X" queries)

When the layer's native geometry is a POINT (Building) the reference is unambiguous. For LineStrings (Street) and Polygons (Tract, CCA) we have to *pick* a representative point — and the choice matters because a polygon shaped like a "C" or a curved street can have its math centroid sit outside the geometry. This table is the pinned rule.

| Layer | Native geometry | Reference point used for KNN | PostGIS function | Stored as | Why |
|-------|-----------------|------------------------------|------------------|-----------|-----|
| Building | POINT | the point itself (parcel centroid from Assessor) | none — `buildings.location` | `buildings.location` | already a point; nothing to compute |
| Street | (MULTI)LINESTRING | midpoint **along the line's length** | `ST_LineInterpolatePoint(ST_LineMerge(geometry), 0.5)` | computed inline in `gold_street_summary` (cheap) | guaranteed on the line for curved/L-shaped segments; `ST_Centroid` can drift off-line |
| Tract | MULTIPOLYGON | **population-weighted centroid** of the tract itself (single-tract weight = its own population, so this collapses to `ST_PointOnSurface(geometry)` for a single tract; the rule is restated for symmetry with CCA) | `ST_PointOnSurface(geometry)` | `tracts.pop_centroid GEOMETRY(POINT, 4326)` (new column — to add) | guaranteed inside the polygon; matches §5 pop-weighting principle for single-tract case |
| CCA | MULTIPOLYGON | **population-weighted centroid** over contained tracts: `Σ(tract.population × ST_Centroid(tract.geometry)) / Σ(tract.population)` | computed in pipeline; falls back to `ST_PointOnSurface(geometry)` if `tracts.population` not yet loaded | `ccas.pop_centroid GEOMETRY(POINT, 4326)` (new column — to add) | reflects "where the average resident actually is", not the geometric middle of the bounding box |

#### Functions ranked
| Function | Returns | When to use | When NOT to use |
|----------|---------|-------------|-----------------|
| `ST_Centroid(geom)` | mathematical centroid `(Σx/n, Σy/n)` | convex polygons, straight LineStrings | non-convex polygons (lakefront CCAs), curved streets — can fall outside the geometry |
| `ST_PointOnSurface(geom)` | a point **guaranteed inside** the geometry | label placement; fallback when no population data | when you need the most "representative" interior point (it's just any interior point, not the most central) |
| `ST_LineInterpolatePoint(line, 0.5)` | true midpoint along a line's length | every Street KNN | non-line geometries |
| `ST_MaximumInscribedCircle(geom).center` | center of the largest inscribed circle (most visually central) | one-off label placement | per-row pipeline use — too slow on 1.9M geometries |
| pop-weighted centroid (manual SQL) | `Σ(child.population × ST_Centroid(child.geometry)) / Σpopulation` | Tract / CCA — anything where "where do people live" matters more than geometric middle | when child population data isn't loaded yet — fall back to `ST_PointOnSurface` |

#### Rule of thumb
- **Single point of record (Building)** → use the point.
- **Linear feature (Street)** → midpoint along length, never math centroid.
- **Polygon with population inside** → pop-weighted centroid; cache it as a stored column so KNN stays a single GIST lookup.
- **Polygon without population data yet** → `ST_PointOnSurface`; flip to pop-weighted on the next pipeline run after ACS loads.

#### Caveat (mandatory in UI when surfaced)
"Nearest X from a neighborhood" reduces a 4 km wide CCA to one number. When showing nearest-anything at Tract/CCA level, the panel must also surface a coverage metric (`% of population within 0.5 mi of stop`, or `median distance from contained buildings`) to expose the variance the centroid hides. See §11 open question on Tract/CCA "nearest X" semantics.

---

## Section 6 — Per-Source Coverage & Status

### 6.1 Backend pipeline (Python `scripts/`)

| Source | Layer this source feeds | Silver table | Fetcher status | Transformer | Frontend wrapper |
|--------|-------------------------|--------------|----------------|-------------|------------------|
| ACS API | Tract (primary), CCA (rollup) | `tracts`, `ccas` (rollup) | 🟥 stub | 🟥 missing | none |
| CPD | CCA / Tract / Street / Building (spatial) | `cpd_incidents` | 🟥 stub | 🟥 missing | RPC `safety_at_point` ✅ |
| 311 | Building (primary), all (spatial) | `complaints_311` | 🟥 stub | 🟥 missing | RPC `complaints_at_address` ✅ |
| Assessor | Building | `buildings` (creates rows) | 🟥 broken (no `run`) | 🟥 missing | none |
| Treasurer | Building (enrichment) | `buildings` (updates) | 🟥 broken (no `run`) | 🟥 missing | none |
| **CTA GTFS** | Building (KNN) | `cta_stops` | ✅ complete | ✅ `transformers/cta.py` | ✅ `getNearestCTAStop` |
| Parks | Building (KNN) | `parks` | 🟥 stub | 🟥 missing | none |
| Streets centerlines (new — §2) | Street (creates rows) | `streets` | ⚪ not started | ⚪ not started | none |
| Chicago Building Permits (new — §13.21) | Tract / Street / Building (spatial) | `building_permits` (new) | ⚪ not started | ⚪ not started | none |
| ACS extended vars (B19013 / B25002 / B25003 — §13.22) | Tract (primary), CCA (rollup) | `tracts` (new columns) | ⚪ extends ACS fetcher | ⚪ extends ACS transformer | none |
| Chicago Parking Lots (new — §13.23) | Building (KNN) | `parking_lots` (new) | ⚪ not started | ⚪ not started | none |
| CPS Attendance Boundaries (new — §13.24) | Building (point-in-polygon) | `school_boundaries` (new) | ⚪ not started | ⚪ not started | none |

### 6.2 Frontend live APIs (JavaScript `src/lib/api/`)

Per §1.4 every wrapper persists to silver before returning. Client LRUs (`geocodeCache`, etc.) are session perf shims only.

| Source | Layer | Used by | Silver landing (canonical) | Session LRU (perf shim) | Status |
|--------|-------|---------|-----------------------------|-------------------------|--------|
| Google Places | Building | amenity layer, comparison §9.7 | `amenities_cache` (30-day TTL) | none | 🟨 scaffolded `google-places.js` |
| FEMA NFHL | Building | flood zone field | `buildings.flood_zone` + `flood_zone_at` (1yr TTL) | none | 🟨 scaffolded `fema.js` |
| Yelp | Building | vibe + amenity enrichment | `amenities_cache` (30-day TTL) | none | 🟨 scaffolded `yelp.js` |
| Google Maps Geocoding | UI input → Building | search bar, address input | `buildings.location` (cached forever once geocoded) | `geocodeCache` LRU 24h (in-flight typeahead only) | 🟨 scaffolded `google-maps.js` |
| Google Places Autocomplete (§7) | UI input | search-bar typeahead | `address_suggestions_cache(query_norm, results, fetched_at)` (24h TTL — new in `010`) | `geocodeCache` LRU 24h | ⚪ not implemented |
| Mapbox routing | UI input → Building | commute time (§9.7 dim 2) | `commute_cache(building_pin, work_lat, work_lng, mode, minutes, fetched_at)` (30d TTL — new in `010`) | LRU 24h | ⚪ not implemented |
| HowLoud | Building | noise score | `noise_cache(coord_key, score, fetched_at)` (1yr TTL — new in `010`) | none | 🟨 scaffolded |
| AirNow | Building | AQI | `aqi_cache(zip, aqi, primary_pollutant, fetched_at)` (1h TTL — new in `010`) | none | 🟨 scaffolded |
| Rentcast | Building | rent estimate | `buildings.rent_estimate` + `rent_estimate_at` (30d TTL — new in `010`); user override always wins | none | 🟨 scaffolded |
| Illinois Report Card | Building | school metadata | `buildings.school_elem`, `buildings.school_rating`, `school_rating_at` | none | 🟨 scaffolded |

Six rows of 🟥 in §6.1 are the next-implementation backlog. Each has its silver shape pinned by §3.

#### Wrapper contract (every `src/lib/api/{source}.js`)

```js
// Pseudocode — every wrapper resolves only after the silver upsert.
export async function getNoiseScore(lat, lng) {
  const key = coordKey(lat, lng);
  const cached = await sb.from('noise_cache')
    .select('score, fetched_at')
    .eq('coord_key', key)
    .single();
  if (cached && fresh(cached.fetched_at, '1y')) return cached.score;

  const score = await fetchHowLoud(lat, lng);              // raw API call
  await sb.from('noise_cache').upsert({                     // <-- silver-write before return
    coord_key: key, score, fetched_at: new Date(),
  }, { onConflict: 'coord_key' });
  return score;
}
```

---

## Section 7 — Search Bar (typeahead address autocomplete)

The Building view is the default landing once the user picks an address. The address search must be a **typeahead** — every keystroke surfaces a ranked list of Chicago address suggestions. This section is the contract; implementation lives in `src/components/SearchBar.jsx` (currently empty).

### 7.1 UX spec — modeled on Google Search typeahead

- Single text input at the top of the page; placeholder: `e.g., 233 S Wacker Dr`.
- **As-you-type:** every keystroke after 2 characters shows up to 5 ranked suggestions in a dropdown beneath the input — same instant feel as google.com.
- **Match highlighting:** the substring the user has typed is rendered bold inside each suggestion row, the rest dim.
- Debounce keystrokes by **200ms** so we don't hammer the API on fast typing.
- Each suggestion row: street address (with matched substring bolded) · neighborhood/CCA in muted text. Keyboard navigable (↑ ↓ Enter, Esc).
- On select → geocode → set `(lat, lng)` in app state → load Building view (replaces the hardcoded Willis Tower coords used in the CTA slice).
- Empty / cleared input collapses the dropdown; no global state change.
- Errors / no-results state: render an inline `No matches in Chicago` row, never a modal.
- **V2 polish:** recent-searches list shown when input is focused but empty.

### 7.2 Suggestion source — Google Places Autocomplete (Places API New)

- Reuse existing scaffolding: `src/lib/api/google-places.js` and `VITE_GOOGLE_PLACES_KEY`.
- Restrict to Chicago via `locationBias = circle{center: 41.8781,-87.6298, radius: 30000m}` and `includedRegionCodes: ["us"]`.
- Use a **session token** per typing session — Places New API bills autocomplete + final geocode as one session.
- Cache responses keyed by `query.toLowerCase().trim()` in `geocodeCache` (LRU, 24h TTL — already exists in `src/lib/cache/index.js`).
- Final geocode of the selected suggestion goes through `src/lib/api/google-maps.js` and validates result via `validation/index.js → CHICAGO_BOUNDS` before accepting.

**Fallback (V2):** Mapbox Geocoding API typeahead — already have `VITE_MAPBOX_TOKEN`.

### 7.3 Data dictionary entries this surface adds to §6

| Source | Layer | Used by | Cache | Status |
|--------|-------|---------|-------|--------|
| Google Places Autocomplete | UI input (no DB row) | search-bar typeahead | `geocodeCache` LRU 24h | ⚪ not implemented |
| Google Maps Geocoding | UI input → building view | search-bar suggestion-select | `geocodeCache` LRU 24h | 🟨 scaffolded |

---

## Section 8 — Per-Entity Display Contract

When the user is at a CCA polygon, a tract polygon, a street segment, or a building card — *exactly which fields* the UI shows.

Every field rendered with: **value · source · confidence · caveat (if confidence < 8)** per CLAUDE.md "Data Display" rules.

### 8.0 Anti-median rule (mandatory for all aggregated panels)

For any field that's a `_median`, `_avg`, or `_modal` (per §3.7), the panel MUST render its spread alongside the central tendency. **A median without a range is a violation.**

Required render shape for every aggregate:

```
<central tendency>     ← e.g. "$1,387 median rent"
<range>                ← e.g. "$825 – $2,940 across 412 buildings"
<your-fit indicator>   ← e.g. "Within your $1,400 cap: 38% of buildings"
```

The "your-fit indicator" only renders when the user has provided the relevant input (salary, rent cap, work pin, etc.). If no relevant input exists, drop that line — never invent a default to fill it.

For modal categorical aggregates (`grocery_tier_modal`, `flood_zone_modal`), render the modal value plus a tiny inline histogram of `_distribution` rather than min/max:

```
Grocery tier (modal): $$
Across 44 stores within 0.25mi: 8× $ · 23× $$ · 11× $$$ · 2× $$$$
```

This rule applies to every panel below — CCA, Tract, Street. Building (canonical, not aggregated) is exempt because there's no spread to show.

### 8.1 CCA panel — `panels/NeighborhoodPanel.jsx`
*Triggered when: user clicks a CCA polygon at zoom 10–12, or clicks the neighborhood crumb in the breadcrumb.*

| Field | Value | Source | Confidence |
|-------|-------|--------|-----------|
| Name | `ccas.name` | populated by ACS / CCA-boundary fetcher (alongside geometry) | 10/10 |
| Median rent | `ccas.rent_median` (pop-weighted from tracts) | ACS via gold rollup | 8/10 |
| Salary-adjusted surplus | `taxEngine + rent + cost defaults` (live) | tax engine + tracts | 8/10 |
| Violent crime (1yr) | `gold_cca_summary.violent_1yr` | `cpd_incidents` | 7/10 |
| Walk score | `ccas.walk_score` | Walk Score / proxy | 7/10 |
| Vibe score | `ccas.vibe_score` | Yelp | 6/10 (N. Side bias caveat) |
| Displacement risk | `ccas.disp_score` | DePaul IHS + ACS | 7/10 |
| Building count | `gold_cca_summary.building_count` | gold view | 9/10 |
| Avg landlord score | `gold_cca_summary.avg_landlord_score` | gold view | 7/10 |
| Delinquent buildings | `gold_cca_summary.delinquent_buildings` | gold view | 9/10 |
| Tract list (drill-down) | `tracts WHERE cca_id = ?` | FK | 10/10 |

Footer: *"Neighborhood averages can mask block-level differences; drill into a tract or street for finer view."*

### 8.2 Tract panel — `panels/TractPanel.jsx`
*Triggered when: user clicks a tract polygon at zoom 12–14.*

| Field | Value | Source | Confidence |
|-------|-------|--------|-----------|
| Tract ID + label | `tracts.id`, `tracts.name` | Census | 10/10 |
| Containing CCA (link) | `tracts.cca_id` → `ccas` | FK | 10/10 |
| Median rent | `tracts.rent_median` | ACS B25064 | 6/10 |
| Rent margin of error | `tracts.rent_moe` | ACS B25003 | 6/10 |
| Population | `tracts.population` | ACS B01003 | 9/10 |
| Violent crime (5yr) | spatial sum within tract | `cpd_incidents` | 7/10 |
| Walk score | `tracts.walk_score` | Walk Score / proxy | 7/10 |
| Displacement risk | `tracts.disp_score` | DePaul IHS + ACS | 7/10 |
| Building count | `gold_tract_summary.building_count` | gold | 9/10 |
| Avg landlord score | `gold_tract_summary.avg_landlord_score` | gold | 7/10 |
| Streets contained (links) | `streets WHERE streets.tract_id = ?` | new FK | 9/10 |

Footer: *"5-year rolling ACS estimate; sample-size driven margin of error."*

### 8.3 Street panel — `panels/StreetPanel.jsx` (new layer)
*Triggered when: user clicks a street segment at zoom 14–16, or scrolls up from a building.*

| Field | Value | Source | Confidence |
|-------|-------|--------|-----------|
| Street name | `streets.name` | Chicago centerline | 10/10 |
| Address range on segment | `streets.from_addr`–`streets.to_addr` | centerline | 9/10 |
| Containing tract / CCA (links) | `streets.tract_id`, `streets.cca_id` | FK | 10/10 |
| Building count on segment | `gold_street_summary.building_count` | gold (new) | 9/10 |
| Avg landlord score | `gold_street_summary.avg_landlord_score` | gold (new) | 7/10 |
| Violent crime within 100m | `gold_street_summary.violent_5yr` | gold (new) | 7/10 |
| 311 within 100m | `gold_street_summary.complaints_311_5yr` | gold (new) | 9/10 |
| Nearest CTA stop | `gold_street_summary.nearest_cta_*` | KNN | 9/10 |
| Nearest park | KNN from segment centroid | `parks` | 9/10 |
| Flood-zone majority | `gold_street_summary.flood_zone_modal` | FEMA via buildings | 9/10 |
| Grocery / coffee tier mode | `gold_street_summary.grocery_tier_modal` etc. | `amenities_cache` | 7/10 (signal) |

Footer: *"Street-segment aggregates exclude cross-streets; 100m buffer is symmetric (both sides of the street)."*

### 8.4 Building panel — `panels/BuildingPanel.jsx` (default after search)

The building view is the densest panel — three groups of sections.

**Group A — Identity & ownership**

| Field | Value | Source | Confidence |
|-------|-------|--------|-----------|
| Address | `buildings.address` | Assessor | 9/10 |
| PIN | `buildings.pin` | Assessor | 10/10 |
| Containing street / tract / CCA (links) | FKs | derived | 10/10 |
| Owner | `buildings.owner` | Assessor | 9/10 |
| Year built | `buildings.year_built` | Assessor | 9/10 |
| Purchase year + price | `buildings.purchase_year`, `purchase_price` | Assessor | 9/10 |
| Tax current | `buildings.tax_current` | Treasurer | 9/10 |
| Tax annual | `buildings.tax_annual` | Treasurer | 9/10 |

**Group B — Surplus formula** (always visible — never collapsed; per CLAUDE.md "Surplus Formula Visibility")

| Line item | Value | Source | Confidence |
|-----------|-------|--------|-----------|
| Take-home | `taxEngine.calculate(salary)` | IRS 2024 + IL DOR + FICA | 10/10 |
| Rent (user override or estimate) | input or Rentcast | user / Rentcast / ACS tract | 9/10 (user) → 7/10 (Rentcast) → 6/10 (tract) |
| Grocery cost delta | Google Places price_level signal × baseline | `amenities_cache` | 7/10 (signal) |
| Dining cost delta | nearby avg price_level × frequency | `amenities_cache` | 7/10 (signal) |
| Transit cost | CTA pass / driving cost | `cta_stops` proximity | 8/10 |
| Parking delta | free street vs paid garage rate | SpotHero / Chicago Data Portal | 7/10 |
| Healthcare OOP | MIT default, slider | MIT Living Wage | 8/10 |
| Lifestyle | slider | user | 10/10 |
| Savings goal | slider | user | 10/10 |
| **Real surplus** | computed total | derived | per inputs |

**Group C — Building intel (collapsible sections)**

| Section | Fields | Source | Confidence |
|---------|--------|--------|-----------|
| Safety (0.25mi) | `violent_5yr`, `property_5yr` | RPC `safety_at_point` | 7/10 |
| Building violations | `violations_5yr`, `heat_complaints`, `bug_reports` | `complaints_311` (text + spatial) | 9/10 |
| Landlord score | `landlord_score` + component breakdown | composite | 7/10 |
| Flood zone | `flood_zone` | FEMA NFHL | 9/10 |
| School (elementary) | `school_elem` + report-card link | CPS + IL Report Card | 7/10 |
| Nearest CTA stop | already implemented (`NearestCTAStop.jsx`) | `cta_stops` | 9/10 |
| Nearest park | name, distance, acreage | RPC `nearest_park` | 9/10 |
| Amenity layer (16 categories) | grocery, gym, parking, restaurants, coffee, laundry, pet care, medical, urgent care, convenience, liquor, clothing, pharmacy, bank, park, fitness | `amenities_cache` | 7/10 (signal) |
| Composite address score | Financial 40% + Livability 30% + Stability 20% + Opportunity 10% | derived | per components |

Footer: required boilerplate from CLAUDE.md ("Chicago.Intel shows you what public data says…").

### 8.5 Drill-paths

| From | To | How |
|------|-----|-----|
| Building | Street | breadcrumb · click "containing street" |
| Street | Tract | breadcrumb · click "containing tract" |
| Tract | CCA | breadcrumb · click "containing CCA" |
| Map (any zoom) | any entity | click polygon / segment / footprint |
| Search bar | Building | typeahead → select → load BuildingPanel |
| Color-by dropdown | recolors all visible polygons | per CLAUDE.md "Map Behavior" |

**File-tree adjustment:** `src/components/panels/CityPanel.jsx` should be deleted (no City layer); `StreetPanel.jsx` is repurposed for the new Street layer; `TractPanel.jsx` needs to be created.

### 8.6 Zoom-coherent aggregation contract

As the user zooms in and out, the same metric must roll up consistently across layers. **Zoom changes the granularity, not the answer.** A user zooming out from a building to its CCA must see numbers that are honestly the rollup of what they just left, not unrelated values.

#### Pinned rule

For every metric M shown at multiple layers, the value at the parent layer is computed from its children using the §5 aggregation rule for that metric — no parallel pipelines, no second source of truth.

```
M(CCA)    = aggregate(M over all child tracts ∈ CCA)        per §5
M(Tract)  = aggregate(M over all child streets ∈ tract OR
                       all child buildings ∈ tract)          per §5
M(Street) = aggregate(M over all child buildings ∈ street)   per §5
M(Building) = canonical                                       per §3
```

Concrete: if `violent_5yr` at the building level is computed via a 0.25 mi spatial buffer (§3.3), the CCA's `violent_5yr` is `SUM` of incidents inside the CCA polygon — not the sum of building-level buffer counts (which would double-count crimes in the overlap zones). The aggregation rule per layer is pinned in §5; this section just enforces that gold MV definitions follow it.

#### Coherence requirements

1. **Same aggregation rule across the gold MV family.** The four gold MVs (`gold_address_intel`, `gold_street_summary`, `gold_tract_summary`, `gold_cca_summary`) share the same source rows for any given metric, just aggregated differently per §5. Refresh order is leaf-up: building MV first, then street, tract, CCA.
2. **Distribution rolls up too** (§3.7). When CCA color uses `rent_p75` of contained tracts, that value is `percentile_cont(0.75)` over all *buildings* in the CCA — not the average of tract-level p75 values (which would smooth out the spread).
3. **Color score recomputes on viewport change**, not on data change. When the user zooms out, the visible-set changes; the color score normalization in §9.3.1 re-runs against the new viewport's min/max — so the same polygon can shift color depending on what else is on screen. Pinned rule from §9.3.1 ("normalization is over the current viewport, not the city").
4. **Numbers in the side panel match the polygon under the cursor.** If a CCA panel says "violent_5yr = 240" and the user zooms in to a tract whose value is "violent_5yr = 18", `Σ tract.violent_5yr` across the CCA's tracts must equal `240`. The numbers reconcile by definition.
5. **Drilling DOWN never changes the parent's number.** Clicking a tract inside a CCA does not retroactively rewrite the CCA's number based on what tract was clicked.
6. **Drilling UP shows the rollup, with the spread.** Per §8.0, the parent panel shows the central tendency AND the range across its children. So zooming out is informative — the user sees more variance, not less.

#### What this forbids

- Computing `gold_cca_summary.rent_median` directly from CCA-level data when tracts are the canonical source — must roll up through tracts per §5.
- Two MVs computing the same metric via different SQL (one would silently drift from the other).
- A panel showing a number that can't be reproduced by aggregating its children.
- Rendering one zoom level using one source and another zoom level using a different one (e.g. tract panel reading from `cpd_incidents` directly while CCA panel reads from `gold_cca_summary` — both must come from the same rule).

#### Verification step (added to bottom of doc)

For any metric M that appears at multiple layers, a unit test runs:
```sql
SELECT
  c.id,
  c.M  AS cca_value,
  (SELECT SUM/AVG/aggregate(t.M) FROM tracts t WHERE t.cca_id = c.id) AS rolled_up_value
FROM gold_cca_summary c
WHERE ABS(cca_value - rolled_up_value) > tolerance;
```
Any non-empty result is a coherence violation — gold MV SQL diverged from §5. Test runs after every gold refresh; failures block the orchestrator.

---

## Section 9 — Scoring & Personalization Contract

**Hard product principle (CLAUDE.md "What the Tool Must Never Do"):** never emit a recommendation. Never say *"we recommend X"*. The tool shows data, components, confidence; the **user** decides. Personalization is therefore not a recommender — it's a re-ranker / re-colorer driven by transparent inputs.

### 9.1 Two kinds of scores

**A) Native scores** — single-source values, deterministic formulas:

| Score | Formula | Range | Stored on | Confidence |
|-------|---------|-------|-----------|-----------|
| `safety_score` | `1 − normalize(violent_5yr / population)` clamped 0–10 | 0–10 (10 = safest) | `ccas`, `tracts` | 7/10 |
| `walk_score` | amenity-density proxy within 0.25mi (or Walk Score API if licensed) | 0–10 | `ccas`, `tracts` | 7/10 |
| `disp_score` | DePaul IHS displacement risk + ACS time-series, normalized | 0–10 | `ccas`, `tracts` | 7/10 |
| `vibe_score` | Yelp lifestyle density (restaurants + coffee + nightlife) | 0–10 | `ccas` | 6/10 (Yelp North-Side bias caveat required) |
| `landlord_score` | weighted: `−violations_5yr` + `−heat_complaints` + `−bug_reports` + `+tax_current` | 0–10 | `buildings` | 7/10 |
| `affordability` (per layer, per user) | `(take-home − rent − costs − transit − parking − healthcare − lifestyle − savings) / take-home` | -∞–1 | computed live (not stored) | 8–10/10 |

Formulas live in `src/lib/calculations/{safety,walk,landlord,affordability}.js` (folder currently empty). Each function has formula + confidence in a header comment.

**B) Composite indices** (per-building, fixed transparent weights from CLAUDE.md):

| Index | Weight | Components |
|-------|--------|-----------|
| Financial Reality | 40% | affordability + tax + rent stability |
| Livability | 30% | walk + safety + amenity density |
| Stability | 20% | landlord_score + tax_current + tenure |
| Opportunity | 10% | school + transit + job-density (BLS) |

Composite UI must always show the four component bars beside the headline number. Never a black-box single score.

### 9.2 Per-layer scoring rules

| Score | CCA | Tract | Street | Building |
|-------|-----|-------|--------|----------|
| Safety | CPD violent_5yr inside polygon, normalized by sum of `tracts.population` inside | inside tract polygon, normalized by `tracts.population` | inside 100m segment buffer, normalized by length | inside 0.25mi (402m) radius, raw counts |
| Walkability | amenity density inside polygon | inside tract polygon | along segment | within 0.25mi of building |
| Affordability | `salary − pop-weighted rent − default costs` | `salary − tract rent − default costs` | `salary − modal rent of contained buildings − default costs` | `salary − actual rent − actual costs (sliders)` |
| Landlord trust | mean of contained buildings | mean of contained | mean of contained | per-building (canonical) |
| Displacement | pop-weighted from tracts | passthrough | passthrough from tract | passthrough from tract |
| Composite | aggregated from component scores | aggregated | aggregated | **per-building (the canonical instance)** |

Higher-layer composites carry the caveat *"Aggregate of N buildings — drill into a tract or street for the underlying values."*

### 9.3 User inputs that drive re-ranking

| Input | UI control | Effect |
|-------|-----------|--------|
| **Salary** | top-of-page slider | recolors every visible polygon / segment / building live by `affordability(salary)` |
| **Color-by** | dropdown | switches map color encoding (Surplus · Safety · Walkability · Displacement · Landlord) |
| **Cost sliders** (groceries / dining / lifestyle / savings / healthcare) | per-line-item slider in BuildingPanel | adjusts the live surplus formula |
| **Rent override** | input in BuildingPanel | replaces estimate with actual rent (jumps confidence 7/10 → 9/10) |
| **What I care about** (V2) | optional weighted sliders for the four composite components | lets user override the 40/30/20/10 default weights |

### 9.3.1 Color-by is multi-factor — never a single column

The map color for a polygon (green → yellow → red) cannot be a direct rendering of one column like `rent_median`. A polygon with a $1,800 median where 80% of buildings exceed your budget should color differently than one with the same $1,800 median where 40% of buildings fit your budget — same number, opposite story.

**Rule:** every color-by mode is a deterministic, transparent, weighted function of multiple inputs. The user can hover any polygon to see all factors and weights. No opaque single-column rendering.

#### Factor set per color-by mode

| Mode | Factors (deterministic weighted sum) |
|------|--------------------------------------|
| **Surplus** (default) | (a) `rent_median` of polygon · (b) `rent_p75` (worst-case end of spread, §3.7) · (c) user's `take_home(salary)` · (d) % of contained buildings under user's rent cap (`count_under_cap / count`) · (e) `nearest_cta_m` of the polygon's reference point (§5.1) — penalize transit deserts · (f) `disp_score` — high displacement risk demotes |
| **Safety** | (a) `violent_5yr / population` (rate, not count) · (b) `property_5yr / population` · (c) 3-year trend slope (improving polygons get a greener tilt) · (d) hotspot concentration — variance across child blocks (a polygon with all crime on one corner colors differently than one spread evenly) |
| **Walkability** | (a) amenity density within 0.25 mi of polygon reference · (b) park acreage within 0.5 mi · (c) `nearest_cta_m` (penalty if >800 m) · (d) sidewalk-density / centerline-coverage from `streets` (V2) |
| **Displacement** | (a) `disp_score` (DePaul IHS + ACS) · (b) ACS rent trend over the last 3 vintages · (c) ownership turnover from `buildings_history` · (d) tenure ratio from ACS B25003 |
| **Landlord** | (a) `avg_landlord_score` of contained buildings · (b) **spread** (`max - min` — a polygon with consistent landlords colors differently than one with extremes) · (c) violation rate per building (`SUM(violations_5yr) / count`) · (d) % of buildings with `tax_current = false` |

#### How weights are decided

Each mode has a default weight vector pinned in `src/lib/calculations/colorBy.js` (to add). Users can open a "weights" popover to see and adjust them — same UI pattern as the §9.7 weight sliders. Defaults are documented and reviewable; nothing is hidden.

#### How the score becomes a color

```
score_polygon = Σ (weight_factor × normalized_value_factor)
color         = scale(score_polygon, viewport_min, viewport_max)
                  → red (low) ··· yellow (mid) ··· green (high)
```

Two pinned rules:

1. **Normalization is over the current viewport**, not the city. A polygon's color is "good *for what's currently on screen*" — drives the user toward relative judgments instead of absolute claims.
2. **No coloring without enough user input.** If the mode requires user inputs we don't have (e.g. Surplus needs salary), the polygons render in neutral gray with a hint banner: *"Enter your salary to color the map by Surplus."* Never invent a default for a mode that depends on user state.

#### Hover panel — what the user sees

```
Lincoln Park · Surplus · 7.2 / 10
─────────────────────────────────
Median rent ($1,800)        weight 25%   → 5.2
Spread / p75 ($2,400)       weight 15%   → 4.1
Buildings under your cap    weight 30%   → 8.0
Transit access (430m)       weight 15%   → 8.4
Displacement risk           weight 15%   → 6.0
─────────────────────────────────
Composite                              7.2
"Top by your selected metric, in your current view. Not a recommendation."
```

Every component is one click from its source row (per CLAUDE.md "Display a number with its source"). The composite is reproducible by the user with a calculator — that's what "deterministic, transparent" means.

#### What this forbids

- Rendering polygon color as `LERP(red, green, rent_median)` or any single column.
- Hiding the weight vector behind a "magic" composite.
- Coloring a polygon by a factor the user hasn't enabled (e.g. coloring by Surplus before salary is entered).
- Letting two polygons with identical headline metrics receive identical colors when their distributions differ — §3.7 spread fields are required inputs to the color score.

### 9.3.2 Macro + microeconomic factor catalog (with freshness budgets)

The factor sets in §9.3.1 are the *minimum*. The full catalog below adds macroeconomic context (citywide / multi-year forces shaping the polygon) and microeconomic context (block-level forces affecting daily life). Factors are admitted to a color computation only if their underlying data is fresh enough to be honest.

#### Macroeconomic factors (per polygon)

| Factor | What it captures | Source | Refresh (§12.1) | Freshness budget |
|--------|------------------|--------|-----------------|------------------|
| Rent trend (3yr) | direction + magnitude of rent change across last 3 ACS vintages | ACS B25064 | annual | 18 months (2 vintages) |
| Income trend (3yr) | gentrification / decline signal | ACS B19013 | annual | 18 months |
| Tenure ratio | owner-occupied vs renter-occupied — stability proxy | ACS B25003 | annual | 18 months |
| Vacancy rate | supply pressure | ACS B25002 | annual | 18 months |
| Population change | inflow / outflow | ACS B01003 | annual | 18 months |
| Tax base growth | property-tax aggregate trend per polygon | Treasurer multi-year | monthly | 90 days |
| Job density | "can you find work near here" | LEHD LODES (BLS) | annual | 24 months (slow-moving) |
| New construction pipeline | supply coming online | Chicago Data Portal Building Permits | nightly | 30 days |
| Subsidized housing density | mix / stability anchor | HUD Picture of Subsidized Households | annual | 24 months |
| Displacement risk score | composite signal | DePaul IHS + ACS | annual | 18 months |
| School quality trend | multi-year ESSA rating | Illinois Report Card | annual | 18 months |

#### Microeconomic factors (per polygon)

| Factor | What it captures | Source | Refresh (§12.1) | Freshness budget |
|--------|------------------|--------|-----------------|------------------|
| Grocery price tier (modal + spread) | weekly basket cost signal | Google Places price_level | lazy 30d TTL | **30 days** (time-sensitive: prices shift) |
| Dining price tier (modal + spread) | discretionary spend signal | Google Places + Yelp | lazy 30d TTL | 30 days |
| Coffee/breakfast tier | recurring micro-spend | Places | lazy 30d TTL | 30 days |
| Pharmacy / urgent-care density | medical-access cost (time = $) | Places | lazy 30d TTL | 90 days |
| Convenience store density | "I forgot milk" frequency | Places | lazy 30d TTL | 90 days |
| Laundry density (free → paid) | building-vs-laundromat decision | Places + 311 violations | lazy 30d TTL | 90 days |
| Crime trend (3yr slope) | direction matters more than level | CPD | nightly delta | **7 days** (time-sensitive) |
| 311 complaint rate | block-level service quality | 311 | nightly delta | 7 days |
| Heat / bug complaint rate | building-quality micro-signal | 311 | nightly delta | 30 days |
| Parking turnover | street-parking realism | Chicago Data Portal Parking Lots (V2) | quarterly | 90 days |
| Air quality (AQI) | day-of-day livability | AirNow | lazy 1h TTL | **1 hour** (time-sensitive) |
| Noise (HowLoud) | block-level lifestyle | HowLoud | lazy 1yr TTL | 1 year (rarely changes) |
| Park acreage within 0.5 mi | recreation access | Park District | quarterly | 1 year |
| Walk-time to nearest CTA | commute realism | GTFS + KNN | quarterly | 1 year |
| Sidewalk-density / centerline-coverage (V2) | walkability infrastructure | Streets | annual | 2 years |
| Building-stock age distribution | utility cost proxy (older = higher heat) | Assessor `year_built` | monthly | 1 year |
| Owner-occupied % at building level | landlord-vs-resident tension | Assessor `owner` heuristic | monthly | 1 year |

#### Time-sensitivity classification

Every factor is tagged with one of three sensitivity bands. The freshness budget is set per band:

| Band | Examples | Budget | Behavior when stale |
|------|----------|--------|---------------------|
| **Hot** (real-time matters) | AQI, current CPD trend, 311 status flips | source's natural cadence (1h–7d) | **dropped** from the color computation; user sees a hint badge "AQI temporarily excluded — last refresh 6h ago" |
| **Warm** (weekly–monthly matters) | grocery / dining tiers, heat complaints, transit changes | 30–90 days | **down-weighted by 50%** in the color score; UI shows a small ⏱ icon |
| **Cool** (slow-moving) | rent vintage, displacement, school rating, year-built distribution, geometry | 1–2 years | full weight; no freshness penalty unless past budget |

#### Freshness-aware color score

```
score_polygon = Σ (
  weight_factor
  × normalized_value_factor
  × freshness_multiplier(factor, band)
)

freshness_multiplier(factor, band) =
  if fresh-within-budget:        1.0
  if stale (warm band):          0.5
  if stale (hot band):           0.0   -- drop entirely
  if stale (cool band, < 2× bud): 1.0   -- still trusted
  if stale (cool band, > 2× bud): warn but keep at 1.0 -- emit data_freshness_log row
```

Per-factor `fetched_at` / `ingested_at` timestamps drive the multiplier (already present per §12.2 audit columns).

#### What the user sees

1. **Hover panel adds a freshness column.** Each factor row shows "weight %·value·(fresh/⏱/●stale-dropped)".
2. **Polygon corner badge** when ≥1 factor is currently dropped: a small ⓘ → tooltip lists which factors are stale and excluded, and how that would shift the color if they were available. This is the "suggest based on fresh data, accept stale only on cool factors" affordance.
3. **The verdict line in §9.7 dim 1 (Real cost of living)** prepends a freshness disclaimer when any cost-tier factor is past budget: *"Cost factors below reflect data ≥30 days old; current prices may differ."*

#### What this forbids

- Letting a hot-band factor drive the color when its data is past budget — the polygon must color *as if that factor doesn't exist*, not on stale numbers pretending to be current.
- Hiding the freshness multiplier from the user — it's part of the score and must be hover-visible.
- Cherry-picking which timestamp counts — `freshness = NOW() - MIN(fetched_at, ingested_at, source_updated_at)` (oldest signal wins, since any of the three could be stale).
- Mixing macro and micro factors in a way the user can't pull apart — every factor in the score must be tagged Macro or Micro in the hover panel, and the user can mute either group via the weights popover.

### 9.4 The only ranked surface — viewport top-N

There is **no global ranked list** and **no "best neighborhoods" page**. The closest thing to a recommendation is the *visible-viewport top-N list*:

- A side panel renders the top 5 entities at the current zoom layer, sorted by the user's chosen `color-by` metric, restricted to the visible viewport.
- Each row: name · the chosen metric · confidence badge · drill-in.
- Header is verbatim: **"Top by your selected metric, in your current view. Not a recommendation."**
- No ML, no "you might like", no "people similar to you". Ranking is fully reproducible from inputs and data.
- If the user clears the color-by, the side panel clears.

### 9.5 Confidence-aware rendering

- Native score < 8/10 → source link + "What this does not tell you" disclosure (mandatory).
- Composite → all four component bars adjacent — never standalone.
- Aggregate scores at higher layers → caveat *"Aggregate of N buildings — drill into a tract or street for the underlying values."*

### 9.6 Why this approach (and not a recommender)

A recommender would (a) optimize for engagement metrics over user truth, (b) hide the why, (c) violate the founding principle. By making **every input transparent and every weight visible**, we give the user a tool to think with, not an oracle that tells them where to live.

### 9.7 Multi-dimensional comparison — "how does this place compare to the one I'm looking at?"

The viewport top-N list (§9.4) is one ranking on one metric. That's too thin to feel real to a user actually weighing a move. The richer surface is the **comparison-to-anchor** view.

**Anchor model.** The user always has a "current focus" entity (the building or area they searched, or the one they last clicked). Every other entity (candidate building, adjacent street, different CCA) gets compared *to that anchor* across **seven dimensions**, not one.

#### The seven dimensions

| # | Dimension | Components (each individually inspectable) | Layer it asks of |
|---|-----------|--------------------------------------------|------------------|
| 1 | **Real cost of living** | take-home delta, rent delta, grocery price-tier delta, dining tier delta, transit cost, parking delta, healthcare OOP, lifestyle slider | Building (canonical) + rollups visible at street/tract/CCA |
| 2 | **Commute & access** | walk-min to nearest CTA, walk-min to nearest grocery / pharmacy, drive-min to user-supplied work pin (Mapbox routing), nearest park distance | Building |
| 3 | **Safety profile** | violent_5yr (0.25mi), property_5yr, 3-year trend slope, violent within 100m of segment | Building + Street |
| 4 | **Building quality & landlord** | landlord_score, violations_5yr, heat_complaints, bug_reports, tax_current, year_built bucket, owner-occupied heuristic | Building |
| 5 | **Risk exposure** | flood_zone, displacement_risk_band, CPD trend direction, 311 complaint volume on segment | Building + Street |
| 6 | **Lifestyle fit** | amenity density (16 categories within 0.25mi), park acreage within 0.5mi, vibe_score (CCA), noise_score (HowLoud, optional) | Building (with CCA passthrough for vibe) |
| 7 | **Family / education** | school_elem rating (Illinois Report Card), distance to nearest library, distance to nearest urgent care | Building |

#### Each dimension card displays
- **Headline delta** (e.g. `+$143/mo`, `−2 violent incidents`, `−4 walk-min to Red Line`).
- **Direction tag** — better / worse / sideways relative to anchor (color: lime / rose / cyan).
- **2–4 component values** for both anchor and candidate, side by side.
- **Confidence band** — derived from the lowest-confidence component used.
- **Source links** — every component is one click from the original data row.

#### User weighting (the "moving parts")
Each dimension has a 0–10 weight slider. Defaults match the CLAUDE.md composite (Financial 40 / Livability 30 / Stability 20 / Opportunity 10, distributed across the 7 sub-dimensions); user can drag any to 0 or 10. Total comparison score = `Σ (weight × normalized_delta)` — appears **only alongside all seven bars and weights**, never standalone.

#### Trade-off summary

A plain-English paragraph, template-filled (NOT AI-generated), stitches the deltas:

> *"Saves you $187/mo on real surplus (lower rent, similar groceries). Walk to the Red Line is 5 minutes longer. Has 3 more building violations in 5 years and a 'B' rated elementary school vs. 'A' at your anchor. Same flood zone. Verdict: cheaper and quieter, but slower commute and a worse school."*

Required: when any candidate dimension is worse, the verdict line must mention at least one *worse* dimension even if the headline is positive.

#### Examples of variability

- **Renter A** (no car, downtown work, no kids): zeroes parking + school weights, maxes commute. The neighborhood she'd "skip on price" might rank higher when transit access compensates.
- **Renter B** (drives, weekend hiker, asthma): maxes parking, healthcare access, park acreage, noise; surplus and school go to zero. A low-rent block on a noisy arterial drops out.
- **Renter C** (kid, suburban-curious): maxes school + landlord + safety; the affordable apartment in the unsafe zip drops below the slightly pricier one with the better school.

Same dataset, three different rankings — driven by transparent weights the user set.

#### What this surface is NOT

- Not a recommender. Always anchor-relative.
- No ML / no opaque scoring. Score is a deterministic weighted sum the user can recompute by hand.
- No hidden trade-offs. Verdict line required to mention worse dimensions when any exist.
- No price-tier-to-dollars conversion without source.

#### New data dictionary entries this surface implies (added to §3 once approved)

- Crime trend slope (3yr) per CCA / tract / street — derived field, recompute on pipeline run.
- `displacement_risk_band` (categorical: low / med / high) — derived from `disp_score` thresholds.
- User work-pin commute time — frontend-only, computed via Mapbox Directions API on demand, cached in `geocodeCache`.
- Owner-occupied heuristic — derived from `buildings.owner` matching `buildings.address_norm` of the same record.

#### New components to add

- `src/components/sections/CompareCard.jsx` — single dimension card, takes `(anchor, candidate, dimensionSpec)`.
- `src/components/sections/ComparePanel.jsx` — seven cards stacked + weight sliders + trade-off summary.
- `src/lib/calculations/comparison.js` — pure function `compare(anchor, candidate, weights) → { dimensions, score, verdict }`. Heavily unit-testable.

---

## Section 10 — Storage Strategy & Reconciliation

### 10.1 Three storage buckets — pre-stored, materialized, live

| Bucket | What lives here | Refresh trigger | Latency at query time |
|--------|----------------|-----------------|-----------------------|
| **Silver tables** (raw normalized — batch-loaded) | every column from every batch fetcher: `buildings`, `tracts`, `ccas`, `streets`, `cpd_incidents`, `complaints_311`, `cta_stops`, `parks` | quarterly orchestrator + nightly 311/CPD delta | direct row read |
| **Silver tables** (lazy-on-view per §1.4) | `amenities_cache` (Places + Yelp), `aqi_cache` (AirNow), `noise_cache` (HowLoud), `commute_cache` (Mapbox), `address_suggestions_cache` (Places Autocomplete); building columns `flood_zone`, `school_*`, `rent_estimate` | populated on first request per key, refreshed when TTL expires | direct row read after first fetch |
| **Gold materialized views** (denormalized, joined) | `gold_address_intel`, `gold_street_summary` (new), `gold_tract_summary`, `gold_cca_summary`. Pre-joins all spatial relationships and 5-year rollups | refresh at end of every orchestrator run via `refresh_gold_layer()` RPC | single-row lookup |
| **Truly live** (no persistence — computed per request) | surplus given current salary, the 7-dim comparison deltas given current weights, viewport top-N, verdict trade-off line | per request | client computation over already-loaded gold rows |

### 10.2 What's pre-stored per entity (concrete list)

For every Building row in `gold_address_intel`:
- All Assessor + Treasurer columns: `pin`, `address`, `address_norm`, `owner`, `year_built`, `purchase_year`, `purchase_price`, `tax_current`, `tax_annual`, `location`
- Building intel: `violations_5yr`, `heat_complaints`, `bug_reports`, `landlord_score`, `flood_zone`, `school_elem`
- Spatial parents: `cca_id`, `cca_name`, `tract_id`, `street_id` (new)
- Nearest-neighbor caches: `nearest_cta_name`, `nearest_cta_m`, `nearest_cta_lines`, `nearest_park_name`, `nearest_park_m`, `nearest_park_acreage`
- Spatial aggregates: `violent_5yr`, `property_5yr` (within 0.25mi)
- `refreshed_at`

For every Street row in `gold_street_summary` (new):
- `id`, `name`, `from_addr`, `to_addr`, `geometry`, `cca_id`, `tract_id`
- `building_count`, `avg_landlord_score`
- `violent_5yr`, `complaints_311_5yr` (within 100m)
- `flood_zone_modal`, `grocery_tier_modal`, `dining_tier_modal`
- `nearest_cta_name`, `nearest_cta_m`

Tract / CCA: as already in `006_gold_materialized_views.sql`, plus pop-weighted aggregates pinned in §5.

**NOT pre-stored** (computed every request):
- Surplus given salary
- Seven-dimension comparison deltas given current weights
- Viewport top-N
- Verdict trade-off line
- User work-pin commute time

### 10.3 Reconciliation — handling source disagreement

**Canonical join spine: the Cook County PIN.** The Assessor record is source-of-truth for "what is this building". Other sources attach in priority order:
1. Direct PIN match (Treasurer)
2. `address_norm` exact match (311, school assignment, manual data)
3. Spatial fallback `ST_DWithin(record.location, building.location, 100m)` (Places, CPD-attribution, geocoded sources)

A row matching by none → goes to `unmatched_log`, never silently dropped.

#### Conflict resolution table

| Field | When sources disagree | Rule |
|-------|----------------------|------|
| Owner | Assessor vs 311 (often property manager, not LLC) | **Assessor wins.** 311 contact rendered separately as `311 contact: <name>` if different. |
| Address (display) | Assessor `address` vs 311 freeform | **Assessor wins** for canonical display; 311 retains its own. |
| Lat/lng for a building | Assessor recorded coord vs Google geocode | **Assessor wins**, unless missing OR Assessor coord >50m from Google geocode of the same address — then Google wins, with `coord_source = 'google_fallback'`. |
| Tax current | Treasurer is canonical | n/a |
| Year built | Assessor only | n/a |
| Crime point location | CPD coord vs incident report address | **CPD coord wins.** If missing, reverse-geocode → confidence drops to 6/10. |
| 311 → building | `address_norm` (primary), spatial fallback (100m) | Both must agree → 9/10; either alone → 7/10; neither → unmatched_log. |
| Rent for surplus | User input vs Rentcast vs ACS tract median | **User input wins (9/10)**, Rentcast next (7/10), ACS tract last (6/10). Active source always shown. |
| Flood zone | FEMA only | n/a |
| School assignment | Illinois Report Card by RCDT vs CPS attendance boundary spatial lookup | Spatial boundary wins for default; RCDT match enriches with metadata. |
| Walk score | Walk Score API (if licensed) vs amenity-density proxy | Licensed value wins; proxy used as fallback with confidence drop. |

#### Reconciliation pipeline step

A new module `scripts/reconcile.py` runs **after silver loads, before gold refresh**:

1. `reconcile_buildings()` — joins assessor + treasurer by PIN, logs every conflicting field to `data_quality_log`.
2. `attach_311()` — populates per-building counters (`violations_5yr`, `heat_complaints`, `bug_reports`) using address-then-spatial join. Unmatched complaints → `unmatched_log`.
3. `assign_streets()` — populates `buildings.street_id` via KNN within 30m.
4. `assign_polygons()` — populates `tract_id`, `cca_id` on `streets` and `buildings` via `ST_Contains`.
5. `validate_buildings()` — every PIN must have non-null `address`, `location`, valid `tract_id`. Failures → `unmatched_log`, surfaced in pipeline run report.

Orchestrator (`scripts/orchestrator.py`) gets a new step #4.5 (between silver load and gold refresh) calling `reconcile.run(client)`.

#### Audit tables (migration `008_reconciliation_tables.sql`)

```sql
CREATE TABLE data_quality_log (
  id           BIGSERIAL PRIMARY KEY,
  entity_type  TEXT NOT NULL,           -- 'building' | 'street' | …
  entity_id    TEXT NOT NULL,           -- pin | street_id | …
  field        TEXT NOT NULL,           -- 'owner' | 'address' | 'lat_lng' | …
  source_a     TEXT NOT NULL,
  value_a      TEXT,
  source_b     TEXT NOT NULL,
  value_b      TEXT,
  resolution   TEXT NOT NULL,           -- 'source_a_wins' | 'source_b_wins' | 'flagged_for_review'
  run_id       TEXT,
  detected_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX ON data_quality_log(entity_type, entity_id);

CREATE TABLE unmatched_log (
  id           BIGSERIAL PRIMARY KEY,
  source       TEXT NOT NULL,           -- '311' | 'cpd' | 'places' | …
  source_id    TEXT NOT NULL,
  reason       TEXT NOT NULL,           -- 'no_pin_match' | 'no_spatial_match' | 'invalid_coord'
  payload      JSONB NOT NULL,          -- preserved for replay / manual triage
  run_id       TEXT,
  detected_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### 10.4 How reconciliation surfaces in the UI

- A field with a row in `data_quality_log` for this entity gets a small ⚑ badge in the panel.
- Hover / click → modal shows: source A, source B, both values, the resolution rule applied, the `run_id` that detected it.
- This is the "moving parts that make sense when checked" extended into the data layer — the user can see where we made a call.
- Per CLAUDE.md, no field is hidden because it conflicts. Conflicts get displayed *with the conflict*.

### 10.5 Storage size sanity check

| Object | Rough size | Note |
|--------|-----------|------|
| `buildings` (silver) | ~1.9M rows × ~30 cols ≈ 600 MB | |
| `gold_address_intel` (MV) | ~1.9M rows × ~50 cols ≈ 1 GB | dominant |
| `cpd_incidents` | ~1.5M rows × ~10 cols ≈ 250 MB | |
| `complaints_311` | ~500K rows × ~10 cols ≈ 100 MB | |
| `streets` (new) | ~50K × ~10 cols ≈ negligible | |
| `tracts`, `ccas`, `cta_stops`, `parks` | combined ≈ negligible | |
| `amenities_cache` | bounded by 30-day TTL × visited buildings | |
| **Total** | **~2.5 GB** | exceeds Supabase free tier (500 MB). **Forces Supabase Pro at $25/mo** for production. |

**Lazy materialization fallback (open question — §11):** populate `gold_address_intel` only for PINs that have been searched at least once. Cuts initial gold-layer storage by ~99% (from 1 GB to ~10 MB for typical first-month traffic).

---

## Section 11 — Open Questions

These resolve before V1 ship; tracked here so they don't get lost.

| # | Question | Why it matters | Default if unresolved |
|---|----------|---------------|------------------------|
| 1 | Should `street_id` be the centerline-source `street_id`, or a stable hash like `street_name_norm + cca_id`? | source dataset id may change on re-publish; hash is stable but loses provenance | use source `street_id` (V1); add `street_name_norm + cca_id` as a `name_key` secondary index |
| 2 | For ACS 5-year rolling vintage (`2019–23`), do we set `data_vintage` per-row or per-table? | per-row protects against partial reloads | per-row |
| 3 | School FK on `buildings.school_elem` — name string, RCDT code, or boundary lookup? | boundary lookup is more accurate but requires shapefile load | boundary lookup, with RCDT as enrichment metadata |
| 4 | Lazy gold materialization vs full materialization at first | full = simpler, ~$25/mo Pro tier; lazy = stays free longer but adds complexity | full materialization at V1; lazy as a V2 cost optimization |
| 5 | Owner-occupied heuristic precision (`owner` = `address_norm` of same record) — false positive rate? | property managers can register at owner address; LLCs may be legit owner-occupants | flag as 6/10 confidence; add a manual override list later |
| 6 | Crime trend slope window (3yr vs 5yr)? | shorter = noisier, longer = misses recent shifts | 3yr default for "trend"; 5yr stored for "level" |
| 7 | Fallback for when `nearest_cta` returns >2 km away (suburb-edge buildings) | KNN always returns something; the result is meaningless past walking distance | render `>2 km — no walkable transit` with confidence drop |
| 8 | When user changes salary, do we re-fetch top-N or recompute client-side from cached gold rows? | client-side is faster but gold rows must include all components | client-side recomputation; gold rows must carry components, not just final scores |
| 9 | History tables (§12.5) — Postgres triggers vs Python loader for SCD2 writes? | trigger keeps logic in DB and works for direct SQL; loader is easier to debug and test | Python loader as single site of truth; revisit if direct-SQL writes become common |
| 10 | Gold MV refresh granularity — full refresh vs per-PIN incremental? | full refresh on 1.9M rows is ~30s; per-row would need a queue | full `REFRESH MATERIALIZED VIEW CONCURRENTLY` at V1; reconsider once refresh time exceeds nightly window |

---

## Section 12 — Operational Data Lifecycle (refresh, idempotency, change tracking, drift)

This section is the contract for *how* data moves from source to silver to gold over time. §10 covered the layout; §12 covers the lifecycle. Every fetcher must implement these rules; the orchestrator enforces them.

### 12.1 Refresh cadence per source

The fetch frequency is driven by how often the upstream actually changes — pulling more often is wasted budget; pulling less often makes the dashboard stale.

Three fetch modes per source — **seed** (one-off cold start, fattest), **delta** (recurring incremental), **on-view** (lazy). The cadence table covers all three.

| Source | Upstream change rate | Recurring cadence (delta) | Delta lookback (§12.8) | Seed window (§12.9) | Trigger |
|--------|----------------------|----------------------------|--------------------------|----------------------|---------|
| Cook County Assessor | annual valuation cycle, mid-year corrections | **monthly** delta on `last_modified` | 30 days (Assessor frequently re-issues prior months) | full snapshot — all Chicago-township PINs (~860K rows) | `pg_cron` |
| Cook County Treasurer | semi-annual tax bills + payment events | **monthly** delta on `tax_year` + `payment_status` | 30 days | **last 5 tax years** (gives `tax_current` history for `buildings_history`, supports trend lines) | `pg_cron` |
| ACS (B25064 / B25003 / B01003) | new 5-yr vintage drops once/yr (December) | **annual**, when Census API publishes new `acs5` vintage | n/a (vintage replacement, not delta) | latest 5-yr vintage (no extra history needed — ACS is already a rolling window) | `pg_cron` checking vintage flag |
| CPD incidents | published daily by Chicago Data Portal | **nightly** delta on `updated_on > (last_run_ts - lookback)` | 7 days (catches late-arriving facts and crashed runs) | **5 years** (required for §3.3 `violent_5yr` / `property_5yr` aggregations) | `pg_cron` 03:00 CT |
| 311 complaints | published daily | **nightly** delta on `updated_on > (last_run_ts - lookback)` | 7 days (status flips from open → closed must be caught) | **5 years** (required for §3.3 `complaints_311_5yr`) | `pg_cron` 03:15 CT |
| CTA GTFS (`stops.txt`) | quarterly schedule changes | **quarterly** full reload + GTFS-RT alert hook | n/a (full snapshot every run) | full snapshot | `pg_cron` + webhook |
| Chicago Park District | infrequent | **quarterly** | n/a | full snapshot | `pg_cron` |
| Streets centerlines (Socrata `6imu-meau`) | rare | **annual** | n/a | full snapshot (~50K segments) | `pg_cron` |
| Illinois Report Card | annual (school year) | **annual** | n/a | latest school-year snapshot | `pg_cron` |
| FEMA NFHL | dynamic (live API) | n/a — on-view | n/a | n/a — silver fills lazily as buildings get viewed | client (lazy) |
| Google Places (autocomplete + nearby) | dynamic | n/a — on-view (ToS forbids bulk pre-cache) | n/a | n/a | client (lazy) |
| Yelp | dynamic | n/a — on-view | n/a | n/a | client (lazy) |
| Google Maps Geocoding | static per-input | n/a — on-view | n/a | n/a | client (lazy) |
| Mapbox routing | dynamic | n/a — on-view | n/a | n/a | client (lazy) |
| HowLoud | static | n/a — on-view | n/a | n/a | client (lazy) |
| AirNow | hourly | n/a — on-view | n/a | n/a | client (lazy) |
| Rentcast | dynamic | n/a — on-view | n/a | n/a | client (lazy) |

`pipeline_runs` (migration 005) records `source`, `started_at`, `finished_at`, `rows_in`, `rows_upserted`, `rows_skipped`, `last_modified_high_watermark`, **and `mode TEXT NOT NULL CHECK (mode IN ('seed','delta','on_view'))`** (added in `011_pipeline_run_mode.sql` — to add) per fetcher. The next run reads its own row to know where to resume.

### 12.2 Upsert + idempotency contract

**Every fetcher must be re-runnable without producing duplicates or corrupting prior state.** Re-running yesterday's run after a crash must converge to the same silver state, not a doubled one.

#### Idempotency rules
1. **Bronze** is append-only and partitioned by `run_id` (TEXT — matches `pipeline_runs.run_id` in migration 005; format is implementation-chosen, currently a hex-encoded UUIDv4 string). Replaying a run produces a *new* bronze file, never overwrites — the audit trail is preserved.
2. **Silver writes are upserts**, never inserts. Every silver table has a stable natural key:

   | Table | Natural key | Conflict target |
   |-------|-------------|-----------------|
   | `buildings` | `pin` | `(pin)` |
   | `tracts` | `id` (Census GEOID) | `(id)` |
   | `ccas` | `id` | `(id)` |
   | `streets` | `id` (centerline `street_id`) | `(id)` |
   | `cpd_incidents` | `case_number` | `(case_number)` |
   | `complaints_311` | `sr_number` | `(sr_number)` |
   | `cta_stops` | `stop_id` | `(stop_id)` |
   | `parks` | `park_no` | `(park_no)` |
   | `amenities_cache` | `(address_key, source, category)` | composite |

3. **Upsert SQL pattern** — every loader uses this shape:

   ```sql
   INSERT INTO {table} ({cols}) VALUES ({vals})
   ON CONFLICT ({natural_key}) DO UPDATE SET
     {col} = EXCLUDED.{col}, …,
     row_hash = EXCLUDED.row_hash,
     source_updated_at = EXCLUDED.source_updated_at,
     ingested_at = NOW(),
     run_id = EXCLUDED.run_id
   WHERE {table}.row_hash IS DISTINCT FROM EXCLUDED.row_hash;  -- §12.4
   ```
   The trailing `WHERE row_hash IS DISTINCT FROM …` makes the upsert a no-op when nothing changed — keeps `ingested_at` honest and avoids unnecessary MV invalidation.

4. **Run-level transaction.** Each fetcher's silver upsert runs inside a single transaction; on failure the run aborts and the watermark stays at the prior value. Partial writes never leak to gold (gold refresh is a separate orchestrator step).
5. **Deletes are tombstones, not deletions.** When a source removes a row, we set `is_deleted = true` and `deleted_at = NOW()` rather than `DELETE`. Gold MVs filter `WHERE is_deleted = false`. This preserves audit + history.
6. **Dedup at fetch time.** Sources occasionally publish the same primary key twice in one batch (CPD does). Loader keeps the row with the latest `source_updated_at` (or last in the batch if no timestamp), drops the rest into `unmatched_log` with `reason = 'intra_batch_dup'`.

#### Required columns on every silver table (migration 005 added these)
| Column | Purpose |
|--------|---------|
| `row_hash` (TEXT) | SHA-256 of canonical JSON of business columns (excludes `ingested_at`, `run_id`, audit cols). Drives change detection §12.4 |
| `source_updated_at` (TIMESTAMPTZ) | The upstream's "last modified" if exposed; else `NOW()` at fetch |
| `ingested_at` (TIMESTAMPTZ) | When *we* wrote it; updated on every real change |
| `run_id` (TEXT) | matches `pipeline_runs.run_id` (TEXT) in migration 005; lets you bisect any row to the run that produced it. Stored as a hex string (UUIDv4 format) but typed TEXT for cross-language portability |
| `is_deleted` (BOOL DEFAULT false) | Tombstone flag |
| `deleted_at` (TIMESTAMPTZ NULL) | When source removed it |

### 12.3 API rate limits & throttling

| Source | Quota | Loader strategy |
|--------|-------|-----------------|
| Census API (ACS) | 500 req/IP/day, no auth needed; with key effectively unlimited | one batch query per ACS table → ~5 calls per run; use API key |
| Cook County Assessor (Socrata `4ex9-snu5`) | 1,000 req/h anon, higher with app token | bulk CSV download once → in-memory parse → upsert in 5K-row batches |
| Cook County Treasurer | bulk CSV | same as Assessor |
| Chicago Data Portal — CPD (`crimes`), 311, Streets, Parks (Socrata) | 1K/h anon, 10K/h with `X-App-Token` | use app token; paginate `$limit=50000 $offset=…`; sleep `200ms` between pages |
| CTA GTFS | static download | one HTTP fetch per quarter |
| FEMA NFHL | ~1 req/sec soft limit | client-side per-building lazy; backoff on 429 |
| Google Places (New) | $200 free + per-call billing; quota: 600 QPM | client-side debounced 200ms (§7); session tokens; cache 30 days |
| Google Maps Geocoding | 50 QPS, $5 / 1K | client `geocodeCache` 24h LRU |
| Mapbox | 600 req/min on directions; 100K/mo free tier | client LRU 24h |
| Yelp | 5K req/day Fusion | per-building cache 30d; never bulk-fetch |
| HowLoud | per-key TBD | client LRU only |
| AirNow | 500 req/h | client LRU 1h |
| Rentcast | $49/mo plan; quota 5K req/mo | per-building lazy; user override always wins |

#### Throttle pattern (loaders)
```python
# scripts/utils/rate_limiter.py (to add)
class RateLimiter:
    def __init__(self, rps: float, burst: int = 1): ...
    def acquire(self): ...   # blocks until token available

# usage
limiter = RateLimiter(rps=4.5)   # stay under 1K/h Socrata
for page in paginate(...):
    limiter.acquire()
    rows = fetch(page)
```

#### Backoff
- 429 / 5xx → exponential backoff with jitter: `min(60s, 2^attempt + random()*1s)`, max 5 attempts.
- Persistent 429 → fetcher fails the run, writes the failure to `pipeline_runs.error`, watermark unchanged. Next nightly run resumes from same point.

### 12.4 Change detection — knowing when a source row changed

The cheapest way to skip unchanged rows is to ask the source ("give me only rows since `t`"); the most reliable way is to compute a hash and compare. We use both, in order:

#### Detection method per source

| Source | Primary signal | Fallback |
|--------|----------------|----------|
| Socrata sources (CPD, 311, Streets, Parks) | `:updated_at > last_run_ts` filter at API | row_hash diff |
| Assessor / Treasurer (bulk CSV) | no upstream timestamp → row_hash diff is primary | n/a |
| ACS | annual vintage flag (`vintage = '2019-2023'`) | full reload on vintage bump |
| CTA GTFS | `feed_version` in `feed_info.txt` | row_hash diff |
| FEMA / Places / Yelp / etc. | per-row TTL on cached value | force-refresh on TTL expiry |

#### `row_hash` definition

Computed at ingest time, *before* `ingested_at`/`run_id` are stamped:

```python
# scripts/utils/hashing.py (to add)
import hashlib, json
def row_hash(row: dict, ignore=("ingested_at","run_id","row_hash")) -> str:
    canonical = json.dumps(
        {k: v for k, v in sorted(row.items()) if k not in ignore},
        separators=(",", ":"), sort_keys=True, default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
```

The upsert in §12.2 only touches the row when `row_hash IS DISTINCT FROM`. That gives us:
- `ingested_at` = last time the row materially changed.
- `pipeline_runs.rows_upserted` = real-change count, not "rows seen".
- An accurate trigger for invalidating downstream gold MVs (only refresh affected gold rows).

### 12.5 Slowly changing dimensions — keeping history per row

We keep history because (a) "when did the owner change?" is a legitimate user question, (b) crime trend lines need point-in-time accuracy, (c) compliance-style audit queries demand it. We use **SCD Type 2** for the durable entities and **append-only event tables** for the transactional ones.

#### Strategy per table

| Table | Strategy | Why | History table |
|-------|----------|-----|---------------|
| `buildings` | **SCD Type 2** | Owner/price/tax change rarely but materially | `buildings_history` |
| `tracts` | **SCD Type 2** keyed on `(id, vintage)` | ACS vintage rolls every year | rows are immutable per `vintage` |
| `ccas` | passthrough (geometry static) | one row per CCA, no history | n/a |
| `streets` | **SCD Type 2** (rare) | source occasionally re-segments | `streets_history` |
| `cpd_incidents` | **append-only event table** | each row is an event, not a state | n/a |
| `complaints_311` | **append-only event table** + status updates → SCD2 | the *complaint* is an event, but its `status` evolves | `complaints_311_history` for `status` only |
| `cta_stops` | SCD Type 2 (rare) | stops occasionally close | `cta_stops_history` |
| `parks` | SCD Type 2 (rare) | park boundary changes | `parks_history` |
| `amenities_cache` | TTL-only, no history | signal data, not state-of-record | n/a |

#### SCD Type 2 schema (template, applied to `buildings_history` etc.)

```sql
CREATE TABLE buildings_history (
  history_id    BIGSERIAL PRIMARY KEY,
  pin           TEXT NOT NULL,
  -- ALL business columns from buildings, exactly as they were:
  owner         TEXT,
  address       TEXT,
  year_built    INT,
  purchase_year INT,
  purchase_price NUMERIC,
  tax_current   BOOL,
  tax_annual    NUMERIC,
  flood_zone    TEXT,
  -- geometry omitted from history (rarely changes; bloat); add if needed
  -- SCD2 metadata:
  valid_from    TIMESTAMPTZ NOT NULL,
  valid_to      TIMESTAMPTZ,                          -- NULL = currently active
  is_current    BOOL GENERATED ALWAYS AS (valid_to IS NULL) STORED,
  change_type   TEXT NOT NULL,                        -- 'insert' | 'update' | 'tombstone'
  changed_fields TEXT[],                              -- which cols differ from the prior row
  row_hash      TEXT NOT NULL,
  run_id        TEXT                                  -- matches pipeline_runs.run_id (TEXT) in 005
);
CREATE INDEX ON buildings_history(pin, valid_from DESC);
CREATE INDEX ON buildings_history(pin) WHERE is_current = true;
```

#### How a change is captured (loader pseudocode)

Every silver upsert that *actually changes* a row also writes a history row:

```python
# scripts/loaders/_scd.py (to add)
def upsert_with_history(conn, table, history_table, row, key_cols):
    new_hash = row_hash(row)
    with conn.transaction():
        prior = conn.execute(f"SELECT row_hash FROM {table} WHERE {key} = %s", (row[key_cols[0]],)).fetchone()
        if prior and prior["row_hash"] == new_hash:
            return "unchanged"
        # 1. close out the prior history row
        conn.execute(f"""
            UPDATE {history_table}
               SET valid_to = NOW()
             WHERE {key} = %s AND valid_to IS NULL
        """, (row[key_cols[0]],))
        # 2. write a new history row (point-in-time snapshot)
        conn.execute(f"INSERT INTO {history_table} (...) VALUES (...)", row | {"valid_from": NOW(), "change_type": "update" if prior else "insert", ...})
        # 3. upsert silver (current state)
        conn.execute(UPSERT_SQL, ...)
        return "changed"
```

#### Querying history
```sql
-- "What did this building look like on 2025-06-01?"
SELECT *
  FROM buildings_history
 WHERE pin = '17-09-410-014-1015'
   AND valid_from <= '2025-06-01'
   AND (valid_to IS NULL OR valid_to > '2025-06-01');

-- "Which buildings changed owner in the last quarter?"
SELECT pin, owner, valid_from
  FROM buildings_history
 WHERE 'owner' = ANY(changed_fields)
   AND valid_from > NOW() - INTERVAL '90 days';
```

#### What gold sees
Gold MVs always read the **current** silver row (`buildings`, not `buildings_history`). History is for ad-hoc admin queries, the `data_quality_log` ⚑ badge UI (§10.4), and trend lines that explicitly ask for it (e.g. `gold_cca_summary.avg_landlord_score_3yr_trend`).

#### Migration `009_scd_history_tables.sql` (to add) creates
- `buildings_history`, `streets_history`, `cta_stops_history`, `parks_history`, `complaints_311_history`
- A trigger `*_history_trigger` on each parent table that calls `upsert_with_history` from a PL/pgSQL helper, OR (preferred) the same logic in the Python loader. Pick one site of truth — recommend the loader so debugging stays in one language.

### 12.6 Schema drift — when the source changes its shape

Every external source changes its schema eventually (Socrata renames a column, Assessor adds `2026_assessed_value`, Census re-codes a variable, GTFS adds an optional column). We need to *notice* this on the run that introduces it, not three weeks later when a downstream gold MV silently drops to NULL.

#### Detection (in the fetcher, before transform)

```python
# scripts/utils/schema_check.py (to add)
EXPECTED_COLS = {  # per-source, version-stamped
    "cpd_incidents": {"case_number","date","primary_type","latitude","longitude", ...},
    ...
}
def assert_no_drift(source: str, sample_row: dict, run_id: str) -> None:
    expected = EXPECTED_COLS[source]
    actual   = set(sample_row.keys())
    missing  = expected - actual           # column we relied on disappeared
    new      = actual - expected           # source added a column
    if missing:
        raise SchemaDriftError(source, missing=missing, run_id=run_id)
    if new:
        log_drift(source, added=new, run_id=run_id)   # warn, don't fail
```

#### Resolution rules

| Drift type | Action | Why |
|------------|--------|-----|
| **Column removed** that we rely on | Fetcher **fails the run**, watermark untouched, alert via `pipeline_runs.error`. | Silent NULLs are the worst outcome — they corrupt gold without showing up. |
| **Column removed** that we don't use | Logged to `schema_drift_log`, run continues. | Informational. |
| **Column added** | Logged to `schema_drift_log`, run continues. | Decide later whether to map it into silver. |
| **Column type changed** (e.g. INT → TEXT) | Fetcher fails. | Type coercion silently drops bad values. |
| **PK semantics changed** (different ID space) | Fetcher fails; manual schema review required. | This breaks every join. |

#### Audit table (`migration 008` — extend the reconciliation migration)

```sql
CREATE TABLE schema_drift_log (
  id          BIGSERIAL PRIMARY KEY,
  source      TEXT NOT NULL,
  drift_type  TEXT NOT NULL,                -- 'column_added' | 'column_removed' | 'type_changed'
  column_name TEXT,
  old_type    TEXT,
  new_type    TEXT,
  run_id      TEXT,                         -- matches pipeline_runs.run_id (TEXT) in 005
  detected_at TIMESTAMPTZ DEFAULT NOW(),
  resolved_at TIMESTAMPTZ,
  notes       TEXT
);
CREATE INDEX ON schema_drift_log(source, detected_at DESC);
```

#### Versioned expected-schema files

`scripts/contracts/{source}.schema.json` per fetcher — checked into git. A schema bump is a code review item. `assert_no_drift()` reads from there. The hash of the active schema is recorded on every `pipeline_runs` row so we can answer "was this row produced under schema v3 or v4?"

### 12.7 Lookback window (overlap on incremental fetches)

A naive incremental fetch — `WHERE updated_at > last_run_ts` — is wrong in three predictable ways:

1. **Late-arriving facts.** The source publishes a row this morning whose `updated_at` is from three days ago (a back-dated correction, a re-classified incident). Our high-watermark moved past it, so we never see it.
2. **Crashed runs.** Our last run hit a 500 error after writing a few hundred rows but never updated the watermark. The next run thinks it succeeded and skips ahead.
3. **Source clock skew.** The source's `updated_at` precision is at best minute-level; sometimes server clocks are seconds off. Strict `>` filters drop edge rows.

The fix is a **lookback window** on the watermark — we re-fetch a deliberate overlap. Because upsert is idempotent and `WHERE row_hash IS DISTINCT FROM` makes unchanged rows a no-op (§12.2), re-fetching is free in DB terms and only costs API quota.

#### Per-source lookback windows

```text
fetch_window_start = last_run_ts - lookback_days
fetch_window_end   = NOW()
```

Lookback days are pinned in §12.1 (third column of the cadence table) and stored on `scripts/contracts/{source}.config.json` so the value lives in code.

| Source | Lookback | Why |
|--------|----------|-----|
| CPD incidents | 7 days | CPD frequently updates incident classification weeks after the event (e.g. battery → assault upgrade); 7d catches the bulk of these without ballooning quota |
| 311 complaints | 7 days | `status` flips (`Open` → `Completed`) need to be caught; SCD2 history (§12.5) writes a new row each time |
| Cook County Assessor | 30 days | Assessor publishes mid-year corrections that re-stamp `last_modified` weeks back |
| Cook County Treasurer | 30 days | Payment events lag bill issuance; backdated paid_amount updates are common |
| ACS, CTA, Streets, Parks | n/a | These are full-snapshot sources — every run is a backfill |

#### Why this is safe

- **Idempotency:** §12.2 upsert `WHERE row_hash IS DISTINCT FROM` makes re-fetching a no-op when nothing changed.
- **Honesty:** `ingested_at` only advances when a row actually changes, so it correctly answers "when did this value last change?" — not "when did we last fetch it?"
- **Quota:** A 7-day overlap on CPD is ~7K rows extra per nightly run vs. ~1K for a strict-watermark — well inside the 10K/h Socrata quota.
- **History fidelity:** SCD2 (§12.5) only writes new history rows on actual change, so the history table stays clean even though we re-touch overlapping rows.

#### Watermark update rule

```text
on success:
  pipeline_runs.last_modified_high_watermark =
    MAX(source_updated_at across rows seen this run)
on failure:
  watermark unchanged → next run re-tries the same window
```

We **never** advance the watermark past `NOW()` — only past `MAX(observed source_updated_at)` — because doing so would skip rows that arrive between fetch start and fetch end.

### 12.8 Initial backfill — the "fattest" first fetch

The first run of any batch fetcher is fundamentally different from a delta run. It seeds the historical context every aggregation, trend, and SCD2 history depends on. Underbuilding this is the single mistake that makes the dashboard look wrong on day 1.

**Rule:** the seed run pulls **as much history as the source allows + as much as our aggregations need**, whichever is greater. Recurring delta runs trim down from there.

#### Seed window per source

| Source | Seed window | Drives which aggregation / history |
|--------|-------------|-------------------------------------|
| CPD | **5 years** | `gold_address_intel.violent_5yr` / `property_5yr` (§3.3); 3-year crime trend slope (§9.7 dim 5); `gold_cca_summary.violent_1yr` |
| 311 | **5 years** | `gold_address_intel.violations_5yr`, `heat_complaints`, `bug_reports`; trend on segment volume (§3.3) |
| Treasurer | **5 tax years** | `buildings_history` shows owner-paid/delinquent transitions; lets users see "this building first went delinquent in 2022" |
| Assessor | full current snapshot of all Chicago-township PINs | establishes building identity (PIN, owner, year_built, location) — the canonical join spine |
| ACS | latest 5-yr vintage only | ACS *is* a 5-year rolling window — pulling the latest vintage already gives 2019–2023 |
| Streets / Parks / CTA | full current snapshot | static identity tables |
| Illinois Report Card | latest school-year + previous 2 years | trend display on building panel ("School rating: B (was C in 2022)") |

#### How seed runs work

A `mode='seed'` run differs from a `mode='delta'` run in three ways:

1. **No watermark read.** `fetch_window_start` comes from the seed window column above (e.g. `NOW() - INTERVAL '5 years'`), not from `pipeline_runs`.
2. **Larger pagination + longer rate budget.** A 5-year CPD pull is ~1.5M rows over ~30 minutes. The throttle is the same RPS but the run is allocated a longer wall-clock budget.
3. **No SCD2 history rows on seed.** First-ever insert is just an insert — `*_history` gets one row marked `change_type='insert'` per silver row, but we don't synthesize "previous values" we never observed.

Triggered by:
```bash
python -m scripts.orchestrator --source cpd --mode seed
```

Stored on `pipeline_runs.mode`. Once a seed for a source has succeeded, future runs default to `mode='delta'` against the high-watermark.

#### Seed → delta cutover

```text
# After seed completes successfully:
pipeline_runs.last_modified_high_watermark =
  MAX(source_updated_at across all rows in the seed run)

# Next nightly cron run uses delta mode against this watermark, with 7-day lookback (§12.7).
```

If a seed fails partway through:
- bronze files are kept (audit trail)
- silver upserts that succeeded stay (they're idempotent)
- `pipeline_runs.status = 'failed'`
- watermark **not** updated
- next manual run with `--mode seed` resumes — the rows already in silver are no-op upserts

#### Seed timing in practice

| Source | Seed run wall-clock estimate |
|--------|-------------------------------|
| CPD 5yr | ~30 min (1.5M rows, paginated 50K at 4.5 RPS) |
| 311 5yr | ~10 min (~500K rows) |
| Assessor full | ~10 min (CSV download + parse + upsert ~860K rows) |
| Treasurer 5yr | ~5 min |
| ACS | ~1 min (a few hundred rows total — 800 tracts × few variables) |
| CTA / Streets / Parks | <1 min each |

Total cold-start: ~1 hour, single sequential run. Parallelizable (`scripts/orchestrator.py --mode seed --parallel`) to ~30 minutes.

#### Seeding the lazy-on-view sources?

We **do not** pre-seed Google Places, Yelp, FEMA, HowLoud, AirNow, Rentcast, Mapbox, or IL Report Card school assignments. Reasons:

1. **ToS / cost.** Google Places forbids bulk pre-caching; per-call billing on Rentcast/Mapbox would be huge for 860K buildings.
2. **TTL economics.** Most of these have short TTLs (1h for AQI, 24h for geocode, 30d for places). Pre-fetched data goes stale before users view it.
3. **Coverage shape.** Users only view a tiny fraction of buildings. Seeding the whole set wastes 99% of the spend.

Lazy-on-view silver tables (`amenities_cache`, `aqi_cache`, `noise_cache`, `commute_cache`, `address_suggestions_cache`) start empty and fill organically as users explore.

### 12.9 Putting it all together — a single fetcher's contract

To stay consistent, every new fetcher (the 6 still 🟥 in §6.1) must implement, in order:

1. **Read mode** — `seed` (first run) or `delta` (recurring) from CLI flag or `pipeline_runs` lookup.
2. **Compute fetch window:**
   - `mode='seed'` → `fetch_window_start = NOW() - seed_window` (per §12.8 table)
   - `mode='delta'` → `fetch_window_start = last_modified_high_watermark - lookback_days` (per §12.7 table)
3. **Schema-check** the first response page → `assert_no_drift()` (§12.6).
4. **Throttle** every API call via `RateLimiter` (§12.3).
5. **Bronze-write** raw response to `data/bronze/{source}/{run_id}.jsonl.gz` (§1.1).
6. **Transform** to the silver shape from §3 + §13.
7. **Hash** every transformed row → `row_hash` (§12.4).
8. **Upsert** into silver under `ON CONFLICT (natural_key) DO UPDATE … WHERE row_hash IS DISTINCT FROM` (§12.2).
9. **Write history** row to `*_history` for any row that changed (SCD2 tables — §12.5).
10. **Update watermark** to `MAX(source_updated_at observed)` on success only.
11. **Reconcile + gold-refresh** runs once per orchestrator pass after all fetchers complete (§10.3).

`scripts/orchestrator.py` is the single enforcement point — fetchers that skip a step are caught in code review.

---

## Section 13 — Source-by-Source Field Mapping (raw → silver)

What each API actually returns, what each row + column in our silver tables means, and the exact transformation between them. **Authoritative when transformer code disagrees with this section: the dictionary is wrong; fix it, then fix the transformer (per top-of-doc rule).**

Format conventions used below:
- **Endpoint** — URL, auth requirement, response format.
- **Raw row** — what one record looks like coming back from the source (abbreviated).
- **Mapping table** — `raw field` → `our column` with type, transform, and meaning.
- **Row meaning** — what one row in our silver table represents.

---

### 13.1 Cook County Assessor (`buildings` — creates rows)

**Endpoint.** `https://datacatalog.cookcountyil.gov/resource/{dataset}.csv` (Socrata bulk CSV download). Free, no key required for ≤1K rows; app token recommended for 10K+ pulls. Two datasets joined: *Residential Property Characteristics* (`bcnq-qrhu`) for building attributes, *Property Index* (`pjab-aw5n`) for owner + address.

**Raw format.** CSV (UTF-8, comma-delimited, header row). One row = one PIN (parcel).

**Sample raw row** (subset):
```
pin,property_class,township,year_built,bldg_sf,units,exterior_wall,roof_type,...
17094100141015,2-99,WEST CHICAGO,1907,2400,2,Brick,Flat,...
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `pin` (14 chars, no dashes) | `buildings.pin` | TEXT | format with dashes: `XX-XX-XXX-XXX-XXXX` | Cook County Property Index Number — canonical building identity |
| `property_address` | `buildings.address` | TEXT | strip whitespace, title-case | display address |
| derived | `buildings.address_norm` | TEXT | `normalizeAddress()` (lowercase, strip directionals/suffixes, drop unit) | join key for 311 / Places matching (§4) |
| `mailing_address_owner_name` | `buildings.owner` | TEXT | strip whitespace, uppercase | legal owner per Assessor |
| `year_built` | `buildings.year_built` | INT | direct; reject `0` and `>currentyear+1` → NULL | construction year |
| `latest_sale_year` | `buildings.purchase_year` | INT | direct | most recent sale year |
| `latest_sale_price` | `buildings.purchase_price` | BIGINT | strip `$` and `,`; reject negative; cents not stored | most recent sale price in $ |
| `latitude`, `longitude` | `buildings.location` | GEOMETRY(POINT,4326) | `ST_MakePoint(lng,lat)` | parcel centroid (point, not footprint) |

**Row meaning.** One row = one PIN = one parcel = one "building" in our model (multi-unit buildings get one row, not one-per-unit; condo PINs each get their own row). Treasurer enriches (does not create rows). 311 / CPD attach via spatial joins on `location`.

**Notes.** 1.9M PINs total in Cook County; we filter to City of Chicago only (`township IN ('CHICAGO','HYDE PARK','LAKE','LAKE VIEW','NORTH CHICAGO','ROGERS PARK','SOUTH CHICAGO','WEST CHICAGO','JEFFERSON')`) → ~860K rows. Reject rows with NULL `latitude`/`longitude` to `unmatched_log` rather than silently load null geometry.

---

### 13.2 Cook County Treasurer (`buildings` — enriches existing rows)

**Endpoint.** `https://www.cookcountytreasurer.com/searchbypin.aspx` — no public REST API; we use the Socrata mirror `https://datacatalog.cookcountyil.gov/resource/uzyt-m557.csv` (Tax Bills dataset). Free, no key.

**Raw format.** CSV. One row per (PIN, tax_year, installment).

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `pin` | join key only | — | format to dashed PIN | matches `buildings.pin` |
| `tax_year` | not stored (latest only) | — | `MAX(tax_year)` per PIN | filter to most recent |
| `total_amount` (sum across installments) | `buildings.tax_annual` | INT | sum all rows for latest `tax_year`, round to dollar | total annual tax bill in $ |
| `paid_amount` >= `total_amount` | `buildings.tax_current` | BOOLEAN | `paid_amount >= total_amount` for the most recent tax year | true if owner is current; false if any installment unpaid |

**Row meaning.** Treasurer rows describe payment events; we collapse to one summary per PIN by aggregating the latest tax year. NEVER create new building rows — Treasurer-only PINs (rare, usually transient) → `unmatched_log`.

**Notes.** Two installments per year (Mar + Aug). `tax_current = false` for buildings with any open installment as of fetch time — this is what drives `gold_cca_summary.delinquent_buildings`.

---

### 13.3 ACS — American Community Survey (`tracts` + CCA rollup)

**Endpoint.** `https://api.census.gov/data/{vintage}/acs/acs5?get={vars}&for=tract:*&in=state:17%20county:031&key={CENSUS_API_KEY}`. Vintage = `2019-2023` (current). Free, 500 req/day per key.

**Raw format.** JSON nested array. Header in row 0, data in rows 1+.

**Sample raw response:**
```json
[
  ["B25064_001E","B01003_001E","state","county","tract"],
  ["1245",   "4123",   "17","031","010100"],
  ["1387",   "5012",   "17","031","010200"]
]
```

**Variables fetched** (one API call per table):

| Census variable | Meaning | Our column |
|------------------|---------|------------|
| `B25064_001E` | Median gross rent ($) | `tracts.rent_median` |
| `B25064_001M` | Margin of error on `B25064_001E` (90% CI half-width) | `tracts.rent_moe` |
| `B25003_001E` | Total occupied housing units | not stored — used for tenure ratio derivation only |
| `B25003_002E` | Owner-occupied units | derived `tracts.owner_occupied_pct` |
| `B25003_003E` | Renter-occupied units | derived `tracts.renter_occupied_pct` |
| `B01003_001E` | Total population | `tracts.population` (drives pop-weighted aggregations §5) |

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `state + county + tract` (concat) | `tracts.id` | TEXT | `'17031' + tract` (11-char Census GEOID) | tract identity |
| `B25064_001E` | `tracts.rent_median` | INT | `int(value)`; treat `-666666666` and `null` as NULL | median monthly gross rent |
| `B25064_001M` | `tracts.rent_moe` | INT | `int(value)`; treat sentinel as NULL | 90% CI half-width on rent |
| `B01003_001E` | `tracts.population` | INT | `int(value)` | total population in tract |
| derived | `tracts.cca_id` | INT | `ST_Contains(ccas.geometry, ST_PointOnSurface(tracts.geometry))` (single-tract pop-weighted centroid degenerate case, §5.1) | parent CCA |
| from TIGER/Line shapefile (separate fetch) | `tracts.geometry` | MULTIPOLYGON 4326 | parse shapefile, project to 4326 | tract boundary |

**Row meaning.** One row = one Census tract (~4K residents avg). Census provides demographic estimates; geometry comes from TIGER/Line (separate annual fetch).

**Notes.** Census uses sentinels for "data suppressed" (`-666666666`, `-999999999`) — must map to NULL, not store as numeric. ACS publishes new 5-year vintage every December; new vintage = full reload (§12.1).

---

### 13.4 Chicago Data Portal — CPD Crimes (`cpd_incidents`)

**Endpoint.** `https://data.cityofchicago.org/resource/ijzp-q8t2.json?$where=date>'{watermark}'&$limit=50000&$offset={page}` (Socrata SoQL). Free, 1K/h anon, 10K/h with `X-App-Token`.

**Raw format.** JSON array. One element = one incident.

**Sample raw row:**
```json
{
  "id": "13245678",
  "case_number": "JG456789",
  "date": "2024-03-15T14:32:00.000",
  "primary_type": "BATTERY",
  "description": "DOMESTIC BATTERY SIMPLE",
  "iucr": "0486",
  "fbi_code": "08B",
  "arrest": "false",
  "domestic": "true",
  "latitude": "41.8781",
  "longitude": "-87.6298",
  "updated_on": "2024-03-16T08:00:00.000"
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `case_number` | `cpd_incidents.case_number` | TEXT | direct | natural key (not `id` — `id` is Socrata-internal and unstable) |
| `date` | `cpd_incidents.date` | TIMESTAMPTZ | parse ISO 8601 → UTC | incident date (the `date` field is already redacted to nearest block / 4h) |
| `primary_type` | `cpd_incidents.primary_type` | TEXT | uppercase strip | top-level category |
| `iucr` (4-char) | `cpd_incidents.iucr` | TEXT | direct | Illinois Uniform Crime Reporting code |
| derived from `iucr` | `cpd_incidents.type` | TEXT | `'violent'` if `iucr` ∈ {01A, 02, 03, 04A, 04B, 08A, 08B, 09}, else `'property'` | bucket used in §5 spatial sums |
| `arrest` | `cpd_incidents.arrest` | BOOLEAN | `value == 'true'` | arrest made |
| `domestic` | `cpd_incidents.domestic` | BOOLEAN | `value == 'true'` | domestic incident flag |
| `latitude`, `longitude` | `cpd_incidents.location` | GEOMETRY(POINT,4326) | `ST_MakePoint(lng,lat)` | redacted to nearest block — **never the actual coordinate** |
| `updated_on` | `cpd_incidents.source_updated_at` | TIMESTAMPTZ | parse ISO 8601 → UTC | drives §12.4 delta detection |

**Row meaning.** One row = one reported incident. Coordinates are deliberately redacted by CPD to the nearest block centroid + 4-hour bucket — this is privacy preservation, not error. Confidence is 7/10 because of redaction blur.

**Notes.** ~1.5M incidents 2019–present. We keep last 5 years for spatial sums (`date >= NOW() - INTERVAL '5 years'`); older rows tombstoned, not deleted, per §12.2 rule 5. Rows with NULL lat/lng (rare) → `unmatched_log`.

---

### 13.5 Chicago Data Portal — 311 (`complaints_311`)

**Endpoint.** `https://data.cityofchicago.org/resource/v6vf-nfxy.json?$where=created_date>'{watermark}'&$limit=50000`. Same Socrata pattern.

**Raw format.** JSON array.

**Sample raw row:**
```json
{
  "sr_number": "SR23-12345678",
  "sr_type": "Building Violation",
  "sr_short_code": "VIOL",
  "created_date": "2024-04-12T09:15:00.000",
  "last_modified_date": "2024-04-15T14:20:00.000",
  "closed_date": null,
  "status": "Open",
  "street_address": "233 S WACKER DR",
  "city": "CHICAGO",
  "zip_code": "60606",
  "latitude": "41.8786",
  "longitude": "-87.6358"
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `sr_number` | `complaints_311.sr_number` | TEXT | direct | natural key |
| `sr_type` | `complaints_311.sr_type` | TEXT | direct | full category label |
| derived from `sr_type` | `complaints_311.category` | TEXT | bucket map: `'Building Violation'` → `'violation'`, `'No Heat / Pilot Light'` → `'heat'`, `'Bed Bug Complaint'` → `'bedbug'`, etc. | bucket used in §5 / §3.3 |
| `created_date` | `complaints_311.created_date` | TIMESTAMPTZ | parse ISO → UTC | when filed |
| `closed_date` | `complaints_311.closed_date` | TIMESTAMPTZ NULL | parse ISO → UTC; NULL if open | resolution date |
| `status` | `complaints_311.status` | TEXT | direct (`'Open'`/`'Completed'`/`'Cancelled'`) | current state — **changes over time → SCD2 in `complaints_311_history` (§12.5)** |
| `street_address` | `complaints_311.address` | TEXT | direct (display) | freeform address as filed |
| derived | `complaints_311.address_norm` | TEXT | `normalizeAddress()` | join key to `buildings.address_norm` (§4) |
| `latitude`, `longitude` | `complaints_311.location` | GEOMETRY(POINT,4326) | `ST_MakePoint(lng,lat)` | filer-provided coord |
| `last_modified_date` | `complaints_311.source_updated_at` | TIMESTAMPTZ | parse ISO → UTC | drives delta detection AND triggers SCD2 history write when `status` changed |

**Row meaning.** One row = one Service Request. Some SRs span months (open → closed); the row is upserted on every fetch with the latest `status`, and the prior `(status, last_modified_date)` is captured in `complaints_311_history` per §12.5.

---

### 13.6 CTA GTFS (`cta_stops`)

**Endpoint.** `https://www.transitchicago.com/downloads/sch_data/google_transit.zip` — single ZIP, ~5 MB. No auth.

**Raw format.** GTFS spec — multiple `.txt` files inside the ZIP, comma-delimited. We read `stops.txt` (and join `routes.txt` + `stop_times.txt` + `trips.txt` for `lines`).

**Sample raw `stops.txt` row:**
```
stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,wheelchair_boarding
30001,"Jackson/State (Red Line)",41.878153,-87.627419,0,40560,1
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `stop_id` | `cta_stops.stop_id` | TEXT | direct | natural key |
| `stop_name` | `cta_stops.name` | TEXT | strip quotes, strip whitespace | display name |
| `stop_lat`, `stop_lon` | `cta_stops.location` | GEOMETRY(POINT,4326) | `ST_MakePoint(lon,lat)` | stop location |
| derived from `stop_times` ⋈ `trips` ⋈ `routes` | `cta_stops.lines` | TEXT[] | for stop S: `ARRAY(SELECT DISTINCT route_short_name FROM stop_times JOIN trips USING(trip_id) JOIN routes USING(route_id) WHERE stop_id = S)` | which "L" lines serve this stop (`Red`, `Blue`, etc.); bus-only stops get bus route numbers |
| `location_type` | not stored | — | filter `location_type IN (0,1)` (drop entrances/nodes) | Stops vs. stations |
| `wheelchair_boarding` | `cta_stops.wheelchair_boarding` | BOOLEAN | `value = 1` (0=unknown, 2=no) | accessibility |

**Row meaning.** One row = one boarding location. Multi-line stations (Red+Blue at Jackson) appear as **one row** with `lines = {Red,Blue}`.

**Notes.** ~20K rows after filter. GTFS feed_version stamps the ZIP — bumped on schedule changes (§12.4 fallback).

---

### 13.7 Chicago Park District (`parks`)

**Endpoint.** `https://data.cityofchicago.org/resource/ej32-qgdr.geojson` (parks polygons) + `https://data.cityofchicago.org/resource/eix4-gf83.json` (facilities lookup). Socrata, free.

**Raw format.** GeoJSON FeatureCollection.

**Sample raw feature:**
```json
{
  "type": "Feature",
  "properties": {
    "park": "GRANT PARK",
    "park_no": 4,
    "acres": 313.5,
    "facility_type": "PARK"
  },
  "geometry": { "type": "MultiPolygon", "coordinates": [[[...]]] }
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `park_no` | `parks.park_no` | INT | direct | natural key |
| `park` | `parks.name` | TEXT | title-case | display name |
| `acres` | `parks.acreage` | NUMERIC(7,2) | direct | size in acres |
| `geometry` (MultiPolygon) | `parks.boundary` | GEOMETRY(MULTIPOLYGON,4326) | parse GeoJSON | park polygon |
| derived | `parks.location` | GEOMETRY(POINT,4326) | `ST_PointOnSurface(boundary)` (§5.1) | KNN reference point — guaranteed inside the park |

**Row meaning.** One row = one named park. Sub-facilities (playgrounds, fieldhouses) within a park are NOT separate rows here.

---

### 13.8 Chicago Street Centerlines (`streets`)

**Endpoint.** `https://data.cityofchicago.org/resource/6imu-meau.geojson`. Socrata, free.

**Raw format.** GeoJSON FeatureCollection. One feature = one block-level segment.

**Sample raw properties:**
```json
{
  "street_id": "1234567",
  "pre_dir": "N",
  "street_nam": "LINCOLN",
  "street_typ": "AVE",
  "suf_dir": "",
  "l_f_add": 2700, "l_t_add": 2798,
  "r_f_add": 2701, "r_t_add": 2799,
  "tlid": "1004920043"
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `street_id` | `streets.id` | TEXT | direct | natural key |
| `pre_dir + street_nam + street_typ + suf_dir` | `streets.name` | TEXT | concat with single spaces, title-case street_nam, leave dirs/types abbreviated | display name e.g. `"N Lincoln Ave"` |
| derived | `streets.name_norm` | TEXT | `normalizeAddress()` on the full name | search index key |
| `MIN(l_f_add, r_f_add)` | `streets.from_addr` | INT | min of left/right starting address | low end of address range |
| `MAX(l_t_add, r_t_add)` | `streets.to_addr` | INT | max of left/right ending address | high end |
| `geometry` (MultiLineString) | `streets.geometry` | GEOMETRY(MULTILINESTRING,4326) | parse GeoJSON | block-level centerline |
| derived | `streets.cca_id` | INT | `assign_streets_to_polygons()` (migration 007) — `ST_Contains(ccas.geometry, ST_PointOnSurface(geometry))` | parent CCA |
| derived | `streets.tract_id` | TEXT | same pattern with `tracts` | parent tract |

**Row meaning.** One row = one block of street (e.g. 2700 N Lincoln to 2799 N Lincoln). A long street like Lincoln Ave is hundreds of rows.

---

### 13.9 Google Places — Nearby + Details (`amenities_cache`, `source='google'`)

**Endpoint.** Places API (New): `POST https://places.googleapis.com/v1/places:searchNearby` with `locationRestriction.circle.radius=402` (0.25 mi). Auth: `X-Goog-Api-Key: $VITE_GOOGLE_PLACES_KEY`. Billing: $32/1K calls (Nearby Search) + $32/1K (Details for `price_level`); session token bundles autocomplete-then-details for typeahead.

**Raw format.** JSON array of `Place` objects under `places`.

**Sample raw response (subset):**
```json
{
  "places": [
    {
      "id": "ChIJ...",
      "displayName": {"text": "Trader Joe's"},
      "formattedAddress": "1147 S Wabash Ave, Chicago, IL 60605",
      "location": {"latitude": 41.8688, "longitude": -87.6258},
      "primaryType": "supermarket",
      "types": ["supermarket","grocery_store","food","point_of_interest"],
      "priceLevel": "PRICE_LEVEL_INEXPENSIVE",
      "rating": 4.5,
      "userRatingCount": 1843
    }
  ]
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `id` | `amenities_cache.place_id` | TEXT | direct | Google's stable place ID (cache anchor) |
| derived | `amenities_cache.address_key` | TEXT | the `address_norm` of the building this query was issued for | groups results back to the requesting building |
| derived | `amenities_cache.source` | TEXT | constant `'google'` | distinguishes from Yelp rows |
| derived | `amenities_cache.category` | TEXT | bucket `primaryType` → one of 16 categories: grocery / dining / coffee / pharmacy / gym / etc. (mapping table in `transformers/places.py`) | category for §3.4 amenity layer |
| `displayName.text` | `amenities_cache.name` | TEXT | direct | display name |
| `priceLevel` | `amenities_cache.price_level` | INT | enum → int: `INEXPENSIVE`=1, `MODERATE`=2, `EXPENSIVE`=3, `VERY_EXPENSIVE`=4, `FREE`/missing=NULL | $/$$/$$$/$$$$ signal — never converted to $ |
| `rating` | `amenities_cache.rating` | NUMERIC(2,1) | direct | star rating |
| `userRatingCount` | `amenities_cache.review_count` | INT | direct | review count |
| `location.latitude`,`location.longitude` | `amenities_cache.location` | GEOMETRY(POINT,4326) | `ST_MakePoint(lng,lat)` | place location |
| derived | `amenities_cache.fetched_at` | TIMESTAMPTZ | `NOW()` | TTL anchor (30 days) |

**Row meaning.** One row = one Place result for one (building, category) query. The same Trader Joe's appears in the cache once per building that's queried near it (because `address_key` differs) — duplicate `place_id`s are intentional, since they let us answer "which places are near building X" with a single indexed lookup.

**Notes.** Google ToS forbids bulk pre-caching (§1.4 exception). 30-day TTL is the maximum permitted by ToS for retained place data. Lazy on first building view.

---

### 13.10 Yelp Fusion (`amenities_cache`, `source='yelp'`)

**Endpoint.** `GET https://api.yelp.com/v3/businesses/search?latitude={lat}&longitude={lng}&radius=402&limit=50`. Auth: `Authorization: Bearer $YELP_API_KEY`. Quota: 5K req/day.

**Raw format.** JSON. `businesses` array.

**Sample raw row:**
```json
{
  "id": "GjI4DtKxMmSHqd_PzaFZUg",
  "name": "Lou Malnati's Pizzeria",
  "categories": [{"alias": "pizza"}, {"alias": "italian"}],
  "price": "$$",
  "rating": 4.0,
  "review_count": 2104,
  "coordinates": {"latitude": 41.8918, "longitude": -87.6291}
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `id` | `amenities_cache.place_id` | TEXT | direct (Yelp ID, distinct ID space from Google) | Yelp's stable business ID |
| derived | `amenities_cache.source` | TEXT | constant `'yelp'` | distinguishes from Google rows |
| `categories[*].alias` | `amenities_cache.category` | TEXT | first category mapped to our 16-bucket taxonomy | shared bucket with Google rows |
| `name` | `amenities_cache.name` | TEXT | direct | display |
| `price` | `amenities_cache.price_level` | INT | length of `$` string (`$`=1, `$$$$`=4); missing=NULL | aligns with Google's enum |
| `rating` | `amenities_cache.rating` | NUMERIC(2,1) | direct | stars |
| `review_count` | `amenities_cache.review_count` | INT | direct | review count |
| `coordinates.latitude`,`coordinates.longitude` | `amenities_cache.location` | GEOMETRY(POINT,4326) | `ST_MakePoint(lng,lat)` | location |

**Row meaning.** Same as 13.9 but sourced from Yelp. Yelp + Google coexist in the same table; a single restaurant might appear twice (once per source) — gold MV deduplicates by name + location proximity within 25m when surfacing.

**Notes.** Yelp has a documented N. Side density bias (§3.4 confidence 6/10) — keep both sources because Google fills S./W. Side gaps Yelp misses.

---

### 13.11 Google Maps Geocoding (`buildings.location` cache)

**Endpoint.** `GET https://maps.googleapis.com/maps/api/geocode/json?address={query}&components=country:US|locality:Chicago&key=$VITE_GOOGLE_MAPS_KEY`. Billing: $5/1K.

**Raw format.** JSON.

**Sample raw response:**
```json
{
  "status": "OK",
  "results": [{
    "formatted_address": "233 S Wacker Dr, Chicago, IL 60606, USA",
    "place_id": "ChIJ...",
    "geometry": {
      "location": {"lat": 41.8786, "lng": -87.6358},
      "location_type": "ROOFTOP"
    },
    "address_components": [{"types": ["postal_code"], "short_name": "60606"}]
  }]
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `geometry.location.lat`,`lng` | `buildings.location` | GEOMETRY(POINT,4326) | `ST_MakePoint(lng,lat)` — only if `location_type ∈ {ROOFTOP, RANGE_INTERPOLATED}` (skip APPROXIMATE) | persisted forever once geocoded |
| `formatted_address` | not persisted (display only) | — | shown in autocomplete picker | confirms match |
| `address_components[type=postal_code].short_name` | not persisted to silver here; used by AirNow wrapper as the ZIP key | — | first-class ZIP for AQI lookup | zip handoff |

**Row meaning.** Geocoding writes to an existing `buildings` row — never creates a new building. If the geocode resolves to a PIN we don't have, the wrapper rejects the address (data integrity > UX in this case).

**Notes.** Pre-geocoded coords from Assessor are preferred when available; Google Geocoding is the fallback for addresses missing `latitude`/`longitude` from Assessor (or where Assessor coord is >50m from Google geocode → §10.3 reconciliation rule).

---

### 13.12 FEMA NFHL — Flood Zone (`buildings.flood_zone`)

**Endpoint.** `https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query?geometry={lng},{lat}&geometryType=esriGeometryPoint&inSR=4326&f=json`. Free, no key, soft 1 RPS.

**Raw format.** Esri JSON.

**Sample raw response:**
```json
{
  "features": [
    {
      "attributes": {
        "FLD_ZONE": "AE",
        "ZONE_SUBTY": "FLOODWAY",
        "STATIC_BFE": 591.5,
        "DFIRM_ID": "17031C"
      }
    }
  ]
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `attributes.FLD_ZONE` | `buildings.flood_zone` | TEXT | direct (`X` = minimal risk, `A`/`AE` = 1% annual chance, `V` = coastal, etc.); `''` empty → `'X'` (no FEMA mapping = effectively zone X) | flood zone designation |
| derived | `buildings.flood_zone_at` | TIMESTAMPTZ | `NOW()` at time of fetch | TTL anchor (1 year per §12.1) |

**Row meaning.** Each building gets one flood_zone value. Empty `features` array → `flood_zone = 'X'` (FEMA hasn't mapped this point as in any special zone).

---

### 13.13 Illinois Report Card — School Ratings (`buildings.school_*`)

**Endpoint.** `https://www.illinoisreportcard.com/Api/...` — varies; we scrape the public CSV at `https://www.isbe.net/Documents/{vintage}-Report-Card-Public-Data-Set.zip` annually rather than hit the API. Free.

**Raw format.** CSV, ~700 columns per school. We extract a handful.

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `RCDTS` (Region-County-District-Type-School, 15 chars) | join key | — | match against CPS attendance boundary spatial lookup | school identifier |
| `SchoolName` | `buildings.school_elem` | TEXT | derived: spatial point-in-polygon on CPS attendance boundaries (downloaded from CPS GIS), then RCDTS-match for the rating | the elementary school assigned to this building's address |
| `OverallSummativeDesignation` | `buildings.school_rating` | TEXT | direct (`Exemplary` / `Commendable` / `Targeted` / `Comprehensive` / `Lowest`) | annual ESSA designation |
| derived | `buildings.school_rating_at` | TIMESTAMPTZ | `NOW()` at fetch | TTL anchor (annual) |

**Row meaning.** Building's elementary school is determined by which CPS attendance boundary contains its `location` (spatial), then the rating is looked up by RCDTS. Two-step join because RCDTS isn't geocoded.

---

### 13.14 AirNow — AQI (`aqi_cache`)

**Endpoint.** `GET https://www.airnowapi.org/aq/observation/zipCode/current/?zipCode={zip}&distance=25&format=application/json&API_KEY=$AIRNOW_API_KEY`. Free, 500 req/h.

**Raw format.** JSON array (one element per pollutant).

**Sample raw response:**
```json
[
  {
    "DateObserved": "2024-04-26",
    "HourObserved": 14,
    "ReportingArea": "Chicago",
    "ParameterName": "PM2.5",
    "AQI": 42,
    "Category": {"Name": "Good", "Number": 1}
  },
  {
    "ParameterName": "OZONE",
    "AQI": 38,
    "Category": {"Name": "Good", "Number": 1}
  }
]
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| query input | `aqi_cache.zip` | TEXT | direct | natural key |
| `MAX(AQI)` across pollutants | `aqi_cache.aqi` | INT | take the worst pollutant's AQI (EPA convention) | composite AQI |
| `ParameterName` of the max-AQI row | `aqi_cache.primary_pollutant` | TEXT | direct (`PM2.5`, `OZONE`, etc.) | which pollutant drove the score |
| `Category.Name` of the max-AQI row | `aqi_cache.category` | TEXT | direct | "Good" / "Moderate" / "Unhealthy" |
| `DateObserved + HourObserved` | `aqi_cache.source_observed_at` | TIMESTAMPTZ | parse + concat in CT timezone, convert to UTC | when AirNow measured (not when we fetched) |
| derived | `aqi_cache.fetched_at` | TIMESTAMPTZ | `NOW()` | TTL anchor (1 hour) |

**Row meaning.** One row per ZIP. AQI is the max across pollutants per EPA convention.

---

### 13.15 HowLoud — Noise Score (`noise_cache`)

**Endpoint.** `GET https://api.howloud.com/score?lat={lat}&lon={lng}&key=$HOWLOUD_API_KEY`. Paid plan; per-call billing varies.

**Raw format.** JSON.

**Sample raw response:**
```json
{
  "score": 73,
  "components": {
    "traffic": 80,
    "air_traffic": 12,
    "transit": 45,
    "local": 60
  }
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| derived from `(lat, lng)` | `noise_cache.coord_key` | TEXT | `f"lat:{round(lat,5)}|lng:{round(lng,5)}"` | natural key (5dp ≈ 1.1m precision, dedupes near-identical lookups) |
| `lat`, `lng` (request input) | `noise_cache.lat`, `lng` | DOUBLE PRECISION | direct | original coordinates (un-rounded — for audit) |
| `score` | `noise_cache.score` | INT | direct, clamp 0–100 | 0 = silent, 100 = constantly loud (HowLoud convention) |
| `components` | `noise_cache.components` | JSONB | direct | sub-scores: traffic / air_traffic / transit / local |

**Row meaning.** One row = one (lat,lng)-rounded coordinate.

---

### 13.16 Rentcast — Rent Estimate (`buildings.rent_estimate`)

**Endpoint.** `GET https://api.rentcast.io/v1/avm/rent/long-term?address={address}`. Auth: `X-Api-Key: $RENTCAST_KEY`. $49/mo plan, 5K req/mo quota.

**Raw format.** JSON.

**Sample raw response:**
```json
{
  "rent": 2150,
  "rentRangeLow": 1980,
  "rentRangeHigh": 2320,
  "comparables": [{"id":"...","address":"...","rent":2100,"distance":0.12}]
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `rent` | `buildings.rent_estimate` | NUMERIC | direct, `int($rent)` | Rentcast AVM monthly rent in $; **user override always wins (§10.3 reconciliation rule)** |
| derived | `buildings.rent_estimate_at` | TIMESTAMPTZ | `NOW()` | TTL anchor (30 days) |

**Row meaning.** One value per building; user input on the surplus form overrides. `comparables` are not persisted — they're informational only.

---

### 13.17 Mapbox Routing — Commute (`commute_cache`)

**Endpoint.** `GET https://api.mapbox.com/directions/v5/mapbox/{mode}/{building_lng},{building_lat};{work_lng},{work_lat}?access_token=$VITE_MAPBOX_TOKEN`. Free for first 100K req/mo.

**Raw format.** JSON.

**Sample raw response:**
```json
{
  "routes": [
    {
      "duration": 1842.7,
      "distance": 14250.3,
      "geometry": "encoded_polyline_..."
    }
  ]
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| query input | `commute_cache.building_pin`, `work_lat`, `work_lng`, `mode` | composite PK | direct | OD pair + travel mode |
| `routes[0].duration` | `commute_cache.minutes` | INT | `round(seconds / 60)` | travel time in minutes |
| `routes[0].distance` | `commute_cache.distance_m` | INT | `round(meters)` | route distance in meters |
| `geometry` | not persisted | — | drop — too large for cache; re-route on demand if rendering | encoded polyline (drawn live, not stored) |

**Row meaning.** One row per (building, work_pin, mode) tuple. Frontend renders the polyline on demand by re-calling Mapbox; only the duration + distance need persisting because they're what the comparison surface (§9.7 dim 2) consumes.

---

### 13.18 Google Places Autocomplete — Search Bar (`address_suggestions_cache`)

**Endpoint.** `POST https://places.googleapis.com/v1/places:autocomplete` with body `{"input": "...", "locationBias": {"circle": {"center": {...}, "radius": 30000}}, "includedRegionCodes": ["us"], "sessionToken": "..."}`. Auth: `X-Goog-Api-Key`. Per-keystroke billing, but session token bundles autocomplete-then-details into one billed event.

**Raw format.** JSON.

**Sample raw response (subset):**
```json
{
  "suggestions": [
    {
      "placePrediction": {
        "placeId": "ChIJ...",
        "text": {"text": "233 S Wacker Dr, Chicago, IL"},
        "structuredFormat": {
          "mainText": {"text": "233 S Wacker Dr"},
          "secondaryText": {"text": "Chicago, IL, USA"}
        }
      }
    }
  ]
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| query input | `address_suggestions_cache.query_norm` | TEXT | `query.toLowerCase().trim()` | natural key |
| `suggestions[*]` | `address_suggestions_cache.results` | JSONB | array of `{place_id, description, structured_formatting}` (5 max) | raw suggestion list rendered in dropdown |
| request session token | `address_suggestions_cache.session_token` | TEXT | direct | needed to bundle with the final geocode for billing |
| derived | `address_suggestions_cache.fetched_at` | TIMESTAMPTZ | `NOW()` | TTL anchor (24 hours) |

**Row meaning.** One row per normalized query string. Two users typing "233 s wacker" share a row.

---

### 13.19 Why some columns appear in the mapping but not in `001_create_tables.sql`

The migration `001_create_tables.sql` predates several columns referenced above (`address_norm`, `arrest`, `domestic`, `category` on 311, `iucr`, `type` on CPD, `wheelchair_boarding`, `rating`, `review_count`, `place_id`). These are part of the §3 schema spec the loaders must implement; they will land in a follow-up migration `011_silver_column_alignment.sql` once their respective fetchers move from 🟥 stub to ✅.

Until then, **the dictionary is the authority** (per top-of-doc rule): the loaders must include these columns in their upserts when each fetcher's silver-write step is implemented.

---

### 13.20 SpotHero — Parking (no public substitute)

SpotHero offers a Partner API for paid parking rates, but partnership is gated. The Chicago Data Portal has no public dataset for paid-garage monthly rates — the earlier §13.23 "Parking Lots (V2)" spec cited dataset `94t9-w7tc`, which does not exist on the portal. The portal returns `dataset.missing` for that ID. Treat §13.23 as void.

For paid garage rates the only paths remain: SpotHero/ParkWhiz partner APIs, Parkopedia / INRIX / HERE (commercial), or OSM `amenity=parking` with `fee=yes` (no rate data). All deferred until there is a current caller for the parking_delta line in §14.8.

What we ingest today instead is §13.27 — Parking Permit Zones — which fixes the more honest gap: telling the truth about whether street parking is actually free at a given address (~30% of Chicago's residential streets sit inside a permit zone).

---

### 13.21 Chicago Building Permits (`building_permits` — new table)

**Endpoint.** `https://data.cityofchicago.org/resource/ydr8-5enu.json?$where=issue_date>'{watermark}'&$limit=50000`. Socrata, free, app token recommended.

**Raw format.** JSON array. One element = one permit.

**Sample raw row** (subset):
```json
{
  "id": "100912345",
  "permit_": "100912345",
  "permit_type": "PERMIT - NEW CONSTRUCTION",
  "review_type": "STANDARD PLAN REVIEW",
  "application_start_date": "2024-01-15T00:00:00.000",
  "issue_date": "2024-03-22T00:00:00.000",
  "processing_time": "67",
  "street_number": "233",
  "street_direction": "S",
  "street_name": "WACKER",
  "suffix": "DR",
  "work_description": "ERECT 50-STORY MIXED-USE BUILDING",
  "total_fee": "84500.00",
  "reported_cost": "240000000",
  "pin1": "17094100141015",
  "latitude": "41.8786",
  "longitude": "-87.6358"
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `id` | `building_permits.id` | TEXT | direct | natural key |
| `permit_type` | `building_permits.permit_type` | TEXT | uppercase strip | category (`NEW CONSTRUCTION`, `RENOVATION`, `EASY PERMIT`, etc.) |
| derived from `permit_type` | `building_permits.category` | TEXT | bucket: `'new_construction'` / `'renovation'` / `'demolition'` / `'other'` | bucket used in §9.3.2 macro factor "construction pipeline" |
| `issue_date` | `building_permits.issue_date` | TIMESTAMPTZ | parse ISO → UTC | when permit was issued (drives delta watermark) |
| `application_start_date` | `building_permits.applied_at` | TIMESTAMPTZ | parse ISO → UTC | when permit was filed |
| `pin1` | `building_permits.pin` | TEXT | format with dashes | FK to `buildings.pin` (NULL if no PIN match) |
| `street_number` + `street_direction` + `street_name` + `suffix` | `building_permits.address` | TEXT | concat with spaces, title-case street | display address |
| derived | `building_permits.address_norm` | TEXT | `normalizeAddress()` (§4) | join key |
| `reported_cost` | `building_permits.reported_cost` | BIGINT | `int(value)`; reject negative → NULL | declared project cost in $ |
| `total_fee` | `building_permits.permit_fee` | NUMERIC(10,2) | direct | city fee paid |
| `latitude`, `longitude` | `building_permits.location` | GEOMETRY(POINT,4326) | `ST_MakePoint(lng,lat)` | site location |

**Row meaning.** One row = one permit issued. Multiple permits can attach to the same PIN (a building under continuous renovation). At the polygon level, `category = 'new_construction'` issued in the last 24 months is the supply-pipeline signal.

**Notes.** Refresh: nightly delta on `issue_date`, 30-day lookback (some permits are back-dated when re-issued). Rows missing both `pin1` AND `latitude`/`longitude` → `unmatched_log`.

**Status.** Bronze-only as of 2026-05-12. Fetcher: `scripts/fetchers/fetch_building_permits.py` (sodapy + 2020-01-01 date floor + paginated). First write: `s3://chicago-intel-bronze/bronze/building_permits/20260512T051346.jsonl.gz` (226,114 rows). Silver table + transformer + reconcile-to-`buildings.pin` land when the data-load freeze lifts and §9.3.2 construction-pipeline factor has a concrete caller.

---

### 13.22 ACS extended variables (B19013 / B25002 / B25003) — extends `tracts`

Same fetcher and endpoint as §13.3 (Census ACS API). Three additional variables loaded in the same call so we keep one fetcher per source.

**Variables added** (one API call per table; combine in fetcher):

| Census variable | Meaning | Our column | Why we want it (§9.3.2) |
|------------------|---------|------------|--------------------------|
| `B19013_001E` | Median household income ($) | `tracts.income_median` | macro income trend |
| `B19013_001M` | Margin of error on `B19013_001E` | `tracts.income_moe` | confidence band |
| `B25002_002E` | Occupied housing units | not stored — used in derivation | denominator for vacancy rate |
| `B25002_003E` | Vacant housing units | derived → `tracts.vacancy_rate` (NUMERIC, 0-1) | macro vacancy factor |
| `B25003_001E` | Total occupied units | not stored — used in derivation | denominator for tenure |
| `B25003_002E` | Owner-occupied units | derived → `tracts.owner_occupied_pct` | macro tenure factor |
| `B25003_003E` | Renter-occupied units | derived → `tracts.renter_occupied_pct` | macro tenure factor |

**Transform rules.**
- `vacancy_rate = B25002_003E / B25002_002E + B25002_003E)` — clamp to [0,1]; NULL if denominator is 0 or sentinel.
- `owner_occupied_pct = B25003_002E / B25003_001E`; NULL on zero divisor.
- `renter_occupied_pct = B25003_003E / B25003_001E`; NULL on zero divisor.
- Sentinel `-666666666` → NULL on every variable (same rule as §13.3).

**CCA rollup.** Pop-weighted (per §5) using `tracts.population` as weights — applies to `income_median` directly. For `vacancy_rate`, `owner_occupied_pct`, `renter_occupied_pct`: sum numerators and denominators across child tracts, then divide (NOT a pop-weighted average — that double-counts).

**Row meaning.** No new rows; same `tracts` row gains five new columns. Same vintage handling as §13.3 (annual full reload on new ACS publication).

---

### 13.23 Chicago Parking Lots (`94t9-w7tc`) — VOID

Earlier draft of this section specced a "Chicago Parking Lots (V2)" dataset at `94t9-w7tc`. That dataset ID does not exist on the Chicago Data Portal (verified — the resource endpoint returns `dataset.missing`). No table, no fetcher, no transformer was ever built. Migration `013` retains `ALTER TABLE parking_lots …` constraints for a table that was never created; those lines are dead and will need to be dropped or made conditional when the next parking-table migration is authored.

Treat this section as void. The real first-step parking source is §13.27 (Parking Permit Zones). For paid-garage rates, see §13.20.

---

### 13.24 CPS Attendance Boundaries (`school_boundaries` — new table)

**Endpoint.** `https://data.cityofchicago.org/resource/5ihw-cbdn.geojson` (Chicago Public Schools — Elementary School Attendance Boundaries SY2425). Free, no key. The earlier draft of this section cited `8wkm-z37x` which does not exist on the portal. CPS publishes a separate dataset ID per school year — `5ihw-cbdn` is the current SY2425 edition; rolling forward annually means updating this ID (and the `DATASET` constant in the fetcher) when CPS releases SY2526.

**Raw format.** GeoJSON FeatureCollection. One feature = one elementary school's attendance area.

**Sample raw feature** (subset):
```json
{
  "type": "Feature",
  "properties": {
    "school_id": "609966",
    "school_nm": "BELL ELEM SCHOOL",
    "rcdts": "150162990252434",
    "grade_cat": "ES",
    "school_yr": "2024-2025"
  },
  "geometry": { "type": "MultiPolygon", "coordinates": [[[...]]] }
}
```

**Mapping table.**

| Raw field | Our column | Type | Transform | Meaning |
|-----------|------------|------|-----------|---------|
| `school_id` | `school_boundaries.school_id` | TEXT | direct | CPS internal ID |
| `rcdts` (15-char) | `school_boundaries.rcdts` | TEXT | direct | join key to Illinois Report Card (§13.13) |
| `school_nm` | `school_boundaries.school_name` | TEXT | title-case | display |
| `grade_cat` | `school_boundaries.grade_category` | TEXT | direct (`'ES'` / `'MS'` / `'HS'`) | currently we ingest only `ES`; filter at fetch |
| `school_yr` | `school_boundaries.school_year` | TEXT | direct (e.g. `'2024-2025'`) | annual vintage |
| `geometry` | `school_boundaries.boundary` | GEOMETRY(MULTIPOLYGON,4326) | parse GeoJSON | attendance area |

**Row meaning.** One row = one elementary school's catchment polygon. Total ~480 elementary boundaries citywide.

**Use.** Replaces the nearest-school approximation in §13.13. Building's `school_elem` is now derived by `ST_Contains(school_boundaries.boundary, buildings.location)` — exact CPS assignment, not nearest. The `rcdts` column then joins to the Illinois Report Card data for the rating.

**Notes.** Refresh annually (boundaries change each school year). Same `is_deleted` tombstone rule as other silver tables.

**Status.** Bronze-only as of 2026-05-12. Fetcher: `scripts/fetchers/fetch_cps_elementary_boundaries.py`. First write: `s3://chicago-intel-bronze/bronze/cps_elementary_boundaries/20260512T051555.jsonl.gz` (356 features — one per elementary catchment).

#### New gold MV column implied
`gold_address_intel.school_elem` switches from "nearest school by distance" to "school whose boundary contains this building" — a quality jump from 7/10 to 9/10 confidence. The rating itself (still 7/10) comes from Illinois Report Card joined on `rcdts`.

---

### 13.25 Why some columns appear in the mapping but not in `001_create_tables.sql`

(Renumbered from §13.19 — same content.)

The migration `001_create_tables.sql` predates several columns referenced above. These are part of the §3 schema spec the loaders must implement; they will land in a follow-up migration `012_silver_column_alignment.sql` once their respective fetchers move from 🟥 stub to ✅. Until then, **the dictionary is the authority** (per top-of-doc rule): the loaders must include these columns in their upserts when each fetcher's silver-write step is implemented.

---

### 13.26 Migration `012` — what these new sources add

When the four new sources in §13.21–24 are wired, migration `012_color_factor_sources.sql` (to add) will create:
- `building_permits` table + indexes (`pin`, `address_norm`, GIST on `location`, `(category, issue_date DESC)`)
- `parking_lots` table + indexes (`location`, `boundary`)
- `school_boundaries` table + indexes (`rcdts`, GIST on `boundary`)
- 5 new columns on `tracts` (`income_median`, `income_moe`, `vacancy_rate`, `owner_occupied_pct`, `renter_occupied_pct`)
- New gold columns: `gold_address_intel.nearest_paid_parking_*`, `gold_*_summary` macro-factor rollups (income / vacancy / tenure / construction-pipeline counts)

Per the no-bloat rule, `012` is NOT written until at least one of these fetchers is being implemented — the spec lives here, the migration lands when needed.

---

### 13.27 Chicago Parking Permit Zones (`u9xt-hiju`) — bronze-only

**Endpoint.** `https://data.cityofchicago.org/resource/u9xt-hiju.geojson` (Socrata, free; `X-App-Token` honored).

**Status.** Bronze-only as of 2026-05-11. Fetcher: `scripts/fetchers/fetch_parking_permit_zones.py`. First write: `s3://chicago-intel-bronze/bronze/parking_permit_zones/20260512T045212.jsonl.gz` (10,372 features). No silver table, no transformer, no loader yet — those land when the data-load freeze lifts and the parking-delta line in §14.8 has a concrete caller.

**Raw shape.** GeoJSON FeatureCollection. `geometry` is null on every feature — this is a segment-level address-range table, not a polygon layer. Each row pairs a street segment with the permit zone that covers it.

**Sample raw feature** (verified from live endpoint):
```json
{
  "type": "Feature",
  "geometry": null,
  "properties": {
    "row_id": "14735",
    "zone": "143",
    "status": "ACTIVE",
    "street_direction": "N",
    "street_name": "KENMORE",
    "street_type": "AVE",
    "second_street_direction": null,
    "address_range_low": "1856",
    "address_range_high": "1856",
    "odd_even": "E",
    "buffer": "N",
    "ward_low": "43",
    "ward_high": "43"
  }
}
```

**Why this dataset.** The Surplus formula's `parking_delta` line currently assumes street parking = $0. That assumption is wrong for any address inside a permit zone — residents need a permit sticker (or guest passes) to park legally. Permit-zone coverage is the variable that turns "is street parking actually free?" from an assumption into a lookup. ~10K rows covering thousands of street segments.

**Known limitations.**
1. **No geometry.** Resolving address-range → polygon requires joining to `streets` (§13.8) by `street_name + direction + type` and clipping to `address_range_low..high`. That join is a silver-layer concern; bronze just stores the raw features.
2. **No rate / pricing.** Permit cost (annual sticker fee + daily guest pass) is set by City of Chicago and lives outside this dataset.
3. **Status filter.** Inactive zones (`status != 'ACTIVE'`) should be excluded at silver time.

**Refresh.** Quarterly is sufficient — permit zone boundaries change infrequently.

---

### 13.28 Chicago Winter Overnight Parking Restrictions (`mcad-r2g5`) — bronze-only

**Endpoint.** `https://data.cityofchicago.org/resource/mcad-r2g5.geojson` (Socrata, free).

**Status.** Bronze-only as of 2026-05-11. Fetcher: `scripts/fetchers/fetch_winter_overnight_restrictions.py`. First write: `s3://chicago-intel-bronze/bronze/winter_overnight_restrictions/20260512T045755.jsonl.gz` (20 features).

**Raw shape.** GeoJSON FeatureCollection. Each feature is a `MultiLineString` of arterial street segments where parking is banned overnight (3am–7am) Dec 1 – Apr 1 regardless of snowfall. Tiny dataset — 20 features cover the named arterials.

**Why this dataset.** Companion to §13.27. Even outside a permit zone, an address on one of these arterials cannot count on free overnight street parking — another correction to the `parking_delta = $0` assumption in §14.8.

**Refresh.** Annually. Designations rarely change.

---

### 13.29 Chicago Snow Route Parking Restrictions (`i6k4-giaj`) — bronze-only

**Endpoint.** `https://data.cityofchicago.org/resource/i6k4-giaj.geojson` (Socrata, free).

**Status.** Bronze-only as of 2026-05-11. Fetcher: `scripts/fetchers/fetch_snow_route_restrictions.py`. First write: `s3://chicago-intel-bronze/bronze/snow_route_restrictions/20260512T045757.jsonl.gz` (144 features).

**Raw shape.** GeoJSON FeatureCollection. Each feature is a `MultiLineString` of streets where parking is banned whenever 2"+ snow accumulates. Activates by snowfall event, not by date.

**Why this dataset.** Same family as §13.27 / §13.28 — another lookup that decides whether $0 street parking is honest for a given address. Activation is weather-driven (event-based), so its contribution to `parking_delta` is probabilistic by season.

**Refresh.** Annually.

---

§13 documents one hop (raw API → silver). §14 documents the full chain end-to-end for the values a user actually sees on screen — bronze → silver → reconcile → gold → frontend → UI label — and what can change the value at each hop. Read this when debugging a "why does the dashboard show X?" question.

### 14.1 Notation

Each lineage block follows the same shape:

```
VALUE: <human-readable thing the user sees>
  ⟵ <hop>: transformation rule, file/SQL pointer
```

Where `⟵` reads "comes from". Top of the block = what the user sees. Bottom of the block = the original API field.

**Affected by** lists what can change the value (cron schedule, TTL, user input, reconcile rule, MV refresh).

### 14.2 Lineage — Owner

```
UI    "Owner: ARIES INVESTMENTS LLC"  (BuildingPanel.jsx → Group A)
  ⟵ frontend: SELECT owner FROM gold_address_intel WHERE pin = ?
GOLD  gold_address_intel.owner
  ⟵ refresh_gold_layer(): passthrough from buildings.owner
SILVER buildings.owner
  ⟵ reconcile_buildings(): Assessor wins over 311 contact (§10.3)
SILVER buildings.owner [Assessor row]
  ⟵ transformer: strip whitespace, uppercase
BRONZE assessor/{run_id}.jsonl.gz → field "mailing_address_owner_name"
  ⟵ fetcher: scripts/fetchers/fetch_assessor.py — bulk CSV download
SOURCE Cook County Assessor — Property Index dataset (Socrata pjab-aw5n)
```

**Confidence:** 9/10. **Affected by:** monthly Assessor delta cron · 30-day lookback (§12.7) · §10.3 reconciliation (Assessor over 311 contact) · gold MV refresh after every pipeline pass.

### 14.3 Lineage — Tax current (delinquent flag)

```
UI    "Tax current: ⚑ Delinquent"  (BuildingPanel.jsx → Group A)
  ⟵ frontend: SELECT tax_current FROM gold_address_intel WHERE pin = ?
GOLD  gold_address_intel.tax_current
  ⟵ passthrough from buildings.tax_current
GOLD  gold_cca_summary.delinquent_buildings  (rollup)
  ⟵ COUNT(*) FILTER (WHERE NOT tax_current) per CCA
SILVER buildings.tax_current
  ⟵ Treasurer enriches Assessor row by PIN match (§10.3 priority 1)
  ⟵ transformer: paid_amount >= total_amount for MAX(tax_year)
BRONZE treasurer/{run_id}.jsonl.gz → fields "paid_amount", "total_amount", "tax_year"
  ⟵ fetcher: scripts/fetchers/fetch_treasurer.py — Socrata CSV mirror
SOURCE Cook County Treasurer (Socrata uzyt-m557)
```

**Confidence:** 9/10. **Affected by:** monthly Treasurer delta · 30-day lookback (catches late payment events) · SCD2 history written to `buildings_history` whenever the flag flips · gold MV refresh.

### 14.4 Lineage — Violent crimes within 0.25 mi (5 years)

```
UI    "Violent: 12 (last 5 yr)"  (BuildingPanel.jsx → Group C, Safety section)
  ⟵ frontend: SELECT violent_5yr FROM gold_address_intel WHERE pin = ?
  ⟵   OR for free-coord click: RPC safety_at_point(lat, lng) (003_create_functions.sql)
GOLD  gold_address_intel.violent_5yr
  ⟵ refresh_gold_layer(): COUNT(*) FROM cpd_incidents
       WHERE type='violent' AND date >= NOW() - INTERVAL '5 years'
       AND ST_DWithin(location, b.location::geography, 402)
SILVER cpd_incidents.type, cpd_incidents.location, cpd_incidents.date
  ⟵ transformer: type = 'violent' if iucr ∈ {01A, 02, 03, 04A, 04B, 08A, 08B, 09} else 'property'
  ⟵ transformer: location = ST_MakePoint(longitude, latitude)
  ⟵ transformer: date = parse ISO 8601 → UTC
BRONZE cpd/{run_id}.jsonl.gz → fields "iucr", "latitude", "longitude", "date"
  ⟵ fetcher: scripts/fetchers/fetch_cpd.py — Socrata SoQL paginated
       $where=updated_on > '{watermark - 7d lookback}'
SOURCE Chicago Data Portal — CPD Crimes (Socrata ijzp-q8t2)
```

**Confidence:** 7/10 (CPD coordinate redaction to nearest block). **Affected by:** nightly cron 03:00 CT · 7-day delta lookback (catches reclassifications) · gold MV refresh window (a crime added at 03:30 won't appear until next pipeline pass) · 5-year window slides forward each night.

### 14.5 Lineage — Median rent (CCA)

```
UI    "Median rent: $1,387/mo"  (NeighborhoodPanel.jsx)
  ⟵ frontend: SELECT rent_median FROM gold_cca_summary WHERE id = ?
GOLD  gold_cca_summary.rent_median
  ⟵ refresh_gold_layer(): passthrough from ccas.rent_median
SILVER ccas.rent_median
  ⟵ pop-weighted rollup (§5):
       Σ(t.rent_median × t.population) / Σ(t.population)
       FROM tracts t WHERE t.cca_id = c.id
SILVER tracts.rent_median, tracts.population
  ⟵ transformer: int(B25064_001E); sentinel -666666666 → NULL
BRONZE acs/{run_id}.jsonl.gz → field "B25064_001E" (median gross rent)
  ⟵ fetcher: scripts/fetchers/fetch_acs.py — JSON, Census API key
       BASE = https://api.census.gov/data/{vintage}/acs/acs5
SOURCE US Census Bureau — ACS 5-year (currently 2019-2023 vintage)
```

**Confidence:** 8/10 at CCA, 6/10 at tract (sample-size MOE). **Affected by:** annual ACS vintage release (December) · NULL handling for suppressed tracts · pop-weighting rule (§5) · gold MV refresh.

### 14.6 Lineage — Nearest CTA stop

```
UI    "Nearest CTA: Jackson/State (Red), 312m"  (NearestCTAStop.jsx + BuildingPanel)
  ⟵ frontend: SELECT nearest_cta_name, nearest_cta_m, nearest_cta_lines
              FROM gold_address_intel WHERE pin = ?
  ⟵   OR free-coord: RPC nearest_cta(lat, lng) (003_create_functions.sql)
GOLD  gold_address_intel.nearest_cta_*
  ⟵ refresh_gold_layer(): KNN via LATERAL — ORDER BY cs.location <-> b.location
       (§5.1 — Building uses its own POINT, no centroid step)
SILVER cta_stops.location, cta_stops.name, cta_stops.lines
  ⟵ transformer: location = ST_MakePoint(stop_lon, stop_lat)
  ⟵ transformer: lines = derived from stop_times ⋈ trips ⋈ routes
       (per-stop array of distinct route_short_name)
BRONZE cta/{run_id}.jsonl.gz → "stop_id", "stop_name", "stop_lat", "stop_lon"
       + stop_times.txt, trips.txt, routes.txt for the lines join
  ⟵ fetcher: scripts/fetchers/fetch_cta.py — full GTFS ZIP download
SOURCE CTA — google_transit.zip
```

**Confidence:** 9/10 (official GTFS coords). **Affected by:** quarterly cron + GTFS-RT alert · full-snapshot reload (no delta) · KNN gets re-computed on every gold refresh · suburb-edge buildings get a >2 km result with §11 #7 caveat.

### 14.7 Lineage — Flood zone

```
UI    "Flood zone: AE (1% annual chance)"  (BuildingPanel.jsx → Group C)
  ⟵ frontend: SELECT flood_zone FROM gold_address_intel WHERE pin = ?
GOLD  gold_address_intel.flood_zone
  ⟵ passthrough from buildings.flood_zone (silver column)
SILVER buildings.flood_zone, buildings.flood_zone_at
  ⟵ wrapper src/lib/api/fema.js (lazy, on first view) — see §1.4 contract
       cache check: is_fresh(flood_zone_at, '1 year')
       fresh → return; stale → refetch + UPSERT
  ⟵ transformer: empty string / no features → 'X' (zone X = no FEMA mapping)
SOURCE FEMA NFHL REST API — point-in-polygon query against FIRM layer 28
```

**Confidence:** 9/10. **Affected by:** lazy on first view · 1-year TTL refresh · empty-features defaulting to 'X' · §1.4 hard rule means wrapper writes silver before returning to React state.

### 14.8 Lineage — Real surplus (the headline number)

This is multi-source and partially user-driven. Showing every input separately is essential — there's no single API to point at.

```
UI    "Real surplus: $1,243/mo"  (BuildingPanel.jsx → Group B, always visible per §8.4)
  ⟵ frontend: pure JS in src/lib/calculations/affordability.js
       computed live every time the user moves a slider — never persisted
  ⟵ formula:  take_home
              − rent_input
              − grocery_delta
              − dining_delta
              − transit_cost
              − parking_delta
              − healthcare_oop
              − lifestyle
              − savings_goal

   each line item:
   ─────────────────────────────────────────────────────────────────
   take_home          ⟵ src/lib/taxEngine.js (IRS 2024 + IL DOR + FICA)
                        Confidence 10/10 (exact law)
   rent_input         ⟵ user override (9/10) > Rentcast buildings.rent_estimate (7/10)
                        > ACS tracts.rent_median (6/10)
   grocery_delta      ⟵ amenities_cache.price_level (signal, never $)
                        Confidence 7/10 (signal). Lazy on first view.
   dining_delta       ⟵ amenities_cache.price_level same
   transit_cost       ⟵ JS function of nearest_cta_m (gold_address_intel)
                        — within walking range → CTA pass; else driving cost
   parking_delta      ⟵ Chicago Data Portal Parking Lots (94t9-w7tc) — V2; today: $0
   healthcare_oop     ⟵ user slider; default = MIT Living Wage (8/10)
   lifestyle, savings ⟵ user sliders only
   ─────────────────────────────────────────────────────────────────
```

**Confidence:** weakest link governs — typically 7/10 for users without a rent override (Rentcast or ACS dominates), 9/10 with override. **Affected by:** every input slider · which rent source wins per §10.3 priority list · whether amenities_cache has been populated for this building yet · gold MV freshness for `nearest_cta_m`.

### 14.9 Lineage — Confidence badge

The dot/number rendered next to every value (per CLAUDE.md "Data Display" rules).

```
UI    "8/10 ●"  (ConfidenceTag.jsx)
  ⟵ frontend: confidence is a static prop from §3 — looked up by field name
       in src/lib/confidence.js (currently empty — needs to be populated
       from §3 Variable × Layer Matrix)
  ⟵ rule: lowest-confidence component wins for composites
  ⟵ rule: if confidence < 7/10, panel must render "What this does not tell you"
       disclosure adjacent to the value (per CLAUDE.md)
SOURCE the §3 confidence column — a static design choice rooted in
       upstream source quality (not derived from data)
```

**Confidence:** N/A — confidence describes data, it isn't data. **Affected by:** §3 changes · upstream source change (rare; documented in changelog).

### 14.10 What can change a value — the universal table

Every lineage chain is exposed to the same set of mutators. When debugging "why is this value X today and not Y?", check these in order:

| Layer | What can change a value | Where to look |
|-------|--------------------------|---------------|
| **Source** | Upstream republished, redacted, or schema-drifted | `schema_drift_log` (§12.6) · CPD/311 release notes |
| **Fetcher** | Cron didn't run · 429 rate limit · run failed | `pipeline_runs.status='failed'` · `pipeline_runs.error_message` |
| **Bronze** | n/a (append-only audit log; never mutates) | — |
| **Transformer** | Bug in our normalize logic (e.g. sentinel handling for ACS) | `transformers/{source}.py` · `unmatched_log` |
| **Loader** | `WHERE row_hash IS DISTINCT FROM` made it a no-op (value didn't actually change upstream) | `pipeline_runs.rows_skipped` |
| **SCD2** | Value flipped → history row in `*_history` shows when | `SELECT * FROM buildings_history WHERE pin = ? ORDER BY valid_from DESC` |
| **Reconcile** | Two sources disagreed → §10.3 rule picked one | `data_quality_log` · ⚑ badge in UI |
| **Gold MV** | Refresh hasn't run since the silver upsert — extremely rare, end of every pipeline pass | `gold_address_intel.refreshed_at` |
| **Frontend wrapper** (lazy paths) | Cache hit served stale-but-fresh-enough silver row | `buildings.flood_zone_at` etc. — TTL in §12.1 |
| **User input** | Salary slider, rent override, weight sliders re-trigger live computation | React state — never written to silver |
| **JS computation** (truly live) | Code path in `src/lib/calculations/*.js` | Path C in §1.4 / data-flow walkthrough |

### 14.11 Worked example — debugging a wrong value

User reports: *"Building shows tax_current = false but I just paid in full."*

Walk the chain backward (§14.3):

1. **UI** — confirm the badge is `gold_address_intel.tax_current = false` (not a frontend stale cache).
2. **Gold MV** — `SELECT tax_current, refreshed_at FROM gold_address_intel WHERE pin = ?`. If `refreshed_at` is older than today's pipeline run, gold is stale (rare). Force a refresh.
3. **Silver** — `SELECT tax_current, ingested_at, run_id FROM buildings WHERE pin = ?`. Compare `ingested_at` to today.
4. **History** — `SELECT * FROM buildings_history WHERE pin = ? ORDER BY valid_from DESC LIMIT 3`. Did `tax_current` flip false → true → false? If so, source republished mid-run.
5. **pipeline_runs** — `SELECT * FROM pipeline_runs_latest WHERE source = 'treasurer'`. Was the last delta run successful? If failed, watermark stayed put — source may have the new value but we haven't fetched yet.
6. **Source** — query Socrata directly: did Treasurer publish the payment yet? Treasurer lags 24–72h after payment.
7. **Reconcile** — `SELECT * FROM data_quality_log WHERE entity_id = ? AND field = 'tax_current'`. Did Assessor + Treasurer disagree? §10.3 says Treasurer wins on tax_current — but log it anyway.

The debug path is the lineage chain in reverse. Every hop has an audit table, a timestamp, or a deterministic rule pinned in this dictionary.

---

## Section 15 — Data integrity & ACID contract

What stops a bad row from becoming a bad number on the dashboard. Built around three layers — Postgres-side constraints, loader-side guards, audit trail.

### 15.1 ACID coverage map

| Property | How we deliver it |
|----------|-------------------|
| **Atomicity** | Each fetcher's silver upsert runs in one transaction (§12.2 rule 4). Failure → rollback. Gold refresh runs separately, so partial silver never leaks. |
| **Consistency** | NOT-NULL + CHECK constraints (§15.2), upsert `WHERE row_hash IS DISTINCT FROM` (§12.2), reconcile rules (§10.3), zoom coherence test (§8.6). |
| **Isolation** | Postgres MVCC for concurrent reads. Per-source advisory lock (§15.4) for write-vs-write between cron and manual runs. `REFRESH MATERIALIZED VIEW CONCURRENTLY` for gold (no read blocking). |
| **Durability** | Postgres WAL on silver. Bronze append-only gzipped JSONL, never overwritten — full replay possible. SCD2 history tables (§12.5) preserve every state change. |

### 15.2 Postgres-side constraints (migration `013`)

| Table | Constraint | What it stops |
|-------|------------|---------------|
| `buildings` | `address_norm IS NOT NULL` | rows that can't join to 311 / Places |
| `buildings` | `purchase_price >= 0` | parser bugs that swallow `$` |
| `buildings` | `tax_annual >= 0` | same |
| `buildings` | `year_built BETWEEN 1830 AND 2100` | sentinel `0`, future years |
| `buildings`, `cpd_incidents`, `complaints_311`, `building_permits`, `parking_lots` | `in_chicago_bbox(location)` | foreign coords from bad geocodes / typos |
| `cpd_incidents` | `type IN ('violent','property','other')` | unbucketed crime categories |
| `complaints_311` | `date IS NOT NULL` | undateable complaints (can't appear in 5-yr windows) |
| `tracts` | `vacancy_rate / owner_pct / renter_pct ∈ [0,1]` | divide-by-zero or sentinel passthrough |
| `tracts` | `population >= 0` | sentinel passthrough |
| `building_permits` | `category IN ('new_construction','renovation','demolition','other')` | unbucketed permit types |
| `parking_lots` | `monthly_rate >= 0`, `capacity >= 0` | parser bugs |

All CHECKs added with `NOT VALID` so existing rows aren't scanned at ALTER time. Future inserts/updates ARE checked. Run `ALTER TABLE x VALIDATE CONSTRAINT name` after a backfill to make it strict.

The `in_chicago_bbox(geom)` SQL function in migration 013 is the single source of truth for the city bbox — referenced by every location CHECK so we never drift between transformer-side bbox filters and DB-side guards.

### 15.3 Loader-side guards (`scripts/utils/validation.py`)

Three checks run inside `load_all()` before each source's silver upsert. Any raise aborts the orchestrator pass before gold refresh — silver stays in its prior known-good state.

| Guard | Check | Default threshold | Failure means |
|-------|-------|-------------------|----------------|
| `acquire_source_lock(client, source)` | `pg_try_advisory_xact_lock` per source | n/a | another run is already loading this source — abort to avoid race |
| `assert_failure_rate(source, rows_in, rows_out)` | `(rows_in - rows_out) / rows_in` ≤ threshold | 10% | bronze→silver drop too high; transformer broken or source schema shifted |
| `assert_row_count_drift(client, source, observed)` | `observed ≥ prior * (1 - threshold)` | 50% | silver count collapsed run-over-run; source endpoint changed or auth broke |

Each guard logs `*_ok` on pass so the run record shows the check actually ran (not just that it didn't throw).

#### Why these specific three

- **Lock** is the only race-protection we need — Postgres MVCC handles concurrent reads, and the upsert pattern handles two writers in different transactions, but two writers from the *same* source can both think they're the authoritative writer for a row and produce non-deterministic SCD2 history. The lock makes "one writer per source per moment" a hard invariant.
- **Failure rate** catches transformer bugs early. A dictionary update to a source schema (§13) that the transformer doesn't follow shows up as 80% drop on the next run — guard fires, run aborts, dev fixes the transformer.
- **Drift** catches source-side breakage early. The Census API rotates a variable code; we still get a 200 OK with no rows; without this guard, gold renders with all-NULL ACS columns. Guard fails the run; user sees yesterday's data instead of garbage.

Three is the floor. Each has a current caller in `load_all()` (no orphan helpers).

### 15.4 Per-source advisory lock (migration `013`)

```sql
CREATE OR REPLACE FUNCTION acquire_source_lock(p_source TEXT)
RETURNS BOOLEAN
LANGUAGE sql AS $$
  SELECT pg_try_advisory_xact_lock(hashtext('chicago_intel.source.' || p_source));
$$;
```

Transaction-scoped — released automatically on COMMIT or ROLLBACK. Each fetcher source maps deterministically to its own lock id via `hashtext`. Two cron runs of `cpd` will race for the same lock; one wins, the other gets `false` and aborts (no harm done — it'll resume on the next cron tick).

### 15.5 What's NOT enforced (deliberately)

These would help but are not worth the complexity at current scale:

- **Per-row schema validation against `scripts/contracts/{source}.schema.json`.** §12.6 has the drift detection at the source level, which is enough — per-row pydantic on 1.5M rows is overkill.
- **Bronze gzip checksum.** gzip's own CRC catches truncation; we'd only add SHA-256 if R2 corrupted a download (Cloudflare hasn't to date).
- **Triggers that mirror CHECKs at the application layer.** Postgres CHECKs already raise; doubling up adds maintenance with no extra safety.
- **Foreign-key cascade on every reference.** `tracts.cca_id REFERENCES ccas(id)` is FK without cascade — we never delete CCAs at runtime, only via migration. Adding cascade is risk without benefit.

### 15.6 What this does NOT cover (out of scope)

- **Source-side errors** (Treasurer publishes a wrong number) — the dictionary can't catch upstream truth issues. §10.3 reconciliation log + ⚑ badge is the surface for "we know this disagreed" but nothing fixes "the world said something wrong".
- **Privacy / PII** — CPD redacts coordinates upstream (§13.4); we don't add another layer.
- **Authorization** — Supabase RLS handles read-side; this section is about write-side correctness.

### 15.7 Verification step (added to bottom of doc)

After `013` lands, the orchestrator must call `validation.acquire_source_lock` + `assert_failure_rate` + `assert_row_count_drift` for every source. Verification step #13 — added below — fails CI if any loader skips a guard.

---

## Verification

After any change to this dictionary:

1. **Schema parity:** every column in `001_create_tables.sql` appears as a row in §3, OR is explicitly marked as a join-only field in §4.
2. **Source parity:** every fetcher in `scripts/fetchers/` and every file in `src/lib/api/` appears in §6.
3. **Confidence parity:** every confidence rating cited in CLAUDE.md "Data Sources & Confidence Reference" appears in §3 with the same value.
4. **Aggregation rules referenced:** every "rollup" entry in §3 cites a rule from §5 (no orphan rollup rules invented inline).
5. **Streets layer self-contained:** §2 contains everything needed to write migration `007_create_streets.sql` and the spatial-assignment job, with no external context required.
6. **Cadence parity:** every fetcher in §12.1 has a corresponding `pg_cron` schedule in `supabase/migrations/` or a documented client-trigger.
7. **Idempotency parity:** every silver table named in §12.2 has its conflict target enforced by a `UNIQUE` (or `PRIMARY KEY`) constraint in `001_create_tables.sql`.
8. **History parity:** every table marked SCD Type 2 in §12.5 has a corresponding `*_history` table in `supabase/migrations/009_*.sql`.
9. **Schema-contract parity:** every fetcher in `scripts/fetchers/` has a `scripts/contracts/{source}.schema.json` checked into git.
10. **Medallion contract parity (§1.4):** every `src/lib/api/*.js` wrapper (other than `supabase.js`) has a corresponding silver landing named in §1.2 and §6.2. No row in §6.2 says "client-side LRU only" — every row names a silver table or column.
11. **No-direct-API-call rule:** `eslint-plugin-no-direct-api-call` (custom) returns zero violations across `src/components/`, `src/pages/`, `src/hooks/`. Any outbound `fetch`/`axios` outside `src/lib/api/` is a build failure.
12. **Zoom coherence (§8.6):** for every metric appearing at >1 layer, the parent gold MV row equals the §5-aggregated rollup of its children. Coherence test runs after every gold refresh; non-empty result blocks the orchestrator.
13. **Integrity guards (§15):** `load_all()` calls `acquire_source_lock` + `assert_failure_rate` + `assert_row_count_drift` for every source before silver upsert. CI greps `scripts/loaders/__init__.py` for the three calls and fails if any is missing.

Spot-check command:
```bash
grep -c '^|' docs/DATA_DICTIONARY.md                                  # row count sanity
grep -E '9/10|8/10|7/10|6/10|signal' docs/DATA_DICTIONARY.md | wc -l  # confidence coverage
grep -E 'ON CONFLICT' supabase/migrations/*.sql | wc -l               # upsert coverage
grep -lr 'row_hash' scripts/loaders/ | wc -l                          # loaders implementing change detection
```

---

## Changelog

- 2026-04-25 — Initial version. 4-layer model (CCA / Tract / Street / Building), 30+ variable rows in §3, seven-dimension comparison surface (§9.7), reconciliation rules (§10.3).
- 2026-04-26 — Added §12 — Operational Data Lifecycle: per-source fetch cadence, upsert + idempotency contract, API rate limits, row-hash change detection, SCD Type 2 history per table, and schema-drift detection. Open Questions extended with #9 (trigger vs loader for SCD writes) and #10 (gold refresh granularity). Verification extended with cadence/idempotency/history/schema-contract parity checks.
- 2026-04-26 — Added §5.1 Reference point per layer for KNN: pins `ST_LineInterpolatePoint(line, 0.5)` for Street midpoints and pop-weighted centroid for Tract/CCA, with `ST_PointOnSurface` as the no-population fallback. Flags that Street's `gold_street_summary` currently uses `ST_Centroid` and should switch to `ST_LineInterpolatePoint` for curved/L-shaped segments.
- 2026-04-26 — Adopted full medallion: added §1.4 Medallion contract (frontend reads only from gold; every external source persists to silver before returning). §1.2 deviation table updated to mark every API as silver-backed (HowLoud / AirNow / Rentcast / Mapbox routing / Illinois Report Card / Google Places Autocomplete promoted from "client-side LRU only" to silver landings). §6.2 rewritten with a Silver-landing column and a wrapper-contract pseudocode block. §10.1 storage-bucket table split: lazy-on-view silver gets its own row; "truly live" narrows to surplus / 7-dim deltas / viewport top-N / verdict. Added Section 2.5 spec for migration `010_lazy_cache_tables.sql` (4 new cache tables: `aqi_cache`, `noise_cache`, `commute_cache`, `address_suggestions_cache`; 5 new columns on `buildings`). Verification gained #10 (medallion contract parity) and #11 (no-direct-API-call eslint rule).
- 2026-04-26 — Wrote migration `010_lazy_cache_tables.sql` matching §2.5 spec. Reconciled `run_id` typing across the dictionary: changed `UUID` → `TEXT` in §2.5 (4 cache tables), §12.2 (idempotency required-columns table), §12.5 (`buildings_history` SCD2 schema), and §12.6 (`schema_drift_log`). Source of truth is `pipeline_runs.run_id TEXT` in migration 005 — value stored as a hex UUIDv4 string but typed TEXT for cross-language portability. Bronze-partition note (§12.2 rule 1) updated accordingly.
- 2026-04-26 — Added §13 Source-by-Source Field Mapping (raw → silver) for all 18 active sources + 2 deferred. Each source documents endpoint + auth + format, raw row sample, full field-by-field mapping (raw field → our column → type → transform → meaning), row meaning, and source-specific notes (e.g. CPD coordinate redaction, Yelp North-Side bias, Google Places ToS caching limit, sentinel handling for ACS suppressed values).
- 2026-04-26 — Added §12.7 Lookback window (incremental backfill overlap) — every delta fetch overshoots the watermark by 7d (CPD/311) or 30d (Assessor/Treasurer) to catch late-arriving facts, crashed runs, and source clock skew; idempotency makes the overlap free in DB terms. Added §12.8 Initial backfill (seed runs) — `mode='seed'` is a one-off cold-start fetch that pulls 5 years of CPD/311/Treasurer history (or full snapshot for static sources) to seed `gold_address_intel.violent_5yr` / `complaints_311_5yr` / `buildings_history` / trend slopes. Renumbered fetcher contract to §12.9 with mode + lookback steps. §12.1 cadence table gained `Delta lookback` and `Seed window` columns. `pipeline_runs` schema gains a `mode` column in migration `011` (to add).
- 2026-04-26 — Wrote migration `011_pipeline_run_mode.sql` extending `pipeline_runs` with: `source TEXT` (per-source canonical row), `mode TEXT CHECK ('seed'|'delta'|'on_view')`, `last_modified_high_watermark`, `fetch_window_start`/`end`, `lookback_days`, row counters (`rows_in`/`rows_upserted`/`rows_skipped`/`rows_tombstoned`), and `schema_hash` for §12.6 drift audit. Added `get_resume_state(source)` SQL helper that returns the watermark + mode + run-count state for the next fetcher run, plus `pipeline_runs_latest` admin view. Idempotent / additive migration — pre-existing `sources TEXT[]` array column is kept for orchestrator-level rollups.
- 2026-04-26 — Added §14 Data Lineage (source → user) — full end-to-end transformation chains for high-value user-visible fields: owner, tax_current, violent_5yr, median rent, nearest CTA, flood zone, real surplus, confidence badge. Each chain shows the API, the bronze field, the silver column, the reconcile rule, the gold MV computation, the frontend SELECT, and the UI label string. Includes a universal "what can change a value" table mapping debug symptoms to audit tables, plus a worked debug example walking the chain backward from a user complaint to root cause.
- 2026-04-26 — Added §3.7 Distribution-aware aggregation (anti-median rule) and §8.0 UI counterpart. Every aggregated metric (`_median`, `_avg`, `_modal`) must carry companion fields (`_min`, `_max`, `_p25`, `_p75`, `_count`) in the same gold MV row, OR `_distribution` JSONB for categorical aggregates. UI rule: every aggregated panel must render `<central tendency>` + `<range across N children>` + `<your-fit indicator>` (when the user has supplied the relevant input). Building panel exempt because it's canonical, not aggregated. Closes the "median hides variance" gap in polygon-level rankings.
- 2026-04-26 — Added §9.3.1 Color-by is multi-factor — pins that polygon green/yellow/red is a deterministic weighted sum of multiple inputs per mode (Surplus / Safety / Walkability / Displacement / Landlord), never a single column like `rent_median`. Includes per-mode factor sets, normalization-over-viewport rule, no-coloring-without-required-input rule, hover-panel transparency contract, and forbidden patterns. Weight vectors live in `src/lib/calculations/colorBy.js` (to add).
- 2026-04-26 — Added §8.6 Zoom-coherent aggregation contract. As the user zooms in and out, every metric must roll up consistently — `Σ` / `AVG` / pop-weighted at each layer per §5, single source of truth across the four gold MVs, leaf-up refresh order, distribution fields (§3.7) roll up too. Forbidden: parallel pipelines, divergent SQL across MVs, a panel showing a number that can't be reproduced by aggregating its children. Coherence test added as Verification step #12 — any drift between parent gold MV and aggregated-children-from-§5 blocks the orchestrator.
- 2026-04-26 — Added §9.3.2 Macro + microeconomic factor catalog with freshness budgets. Macro factors (rent/income trend, tenure, vacancy, tax base growth, job density, construction pipeline, subsidized housing, displacement, school trend) and micro factors (grocery/dining/coffee tiers, pharmacy/urgent-care/convenience density, crime/311 trend, AQI, noise, parks, transit, sidewalks, building age, owner-occupied %). Three time-sensitivity bands (hot / warm / cool) drive freshness budgets — hot factors drop from the score when stale, warm down-weight 50%, cool full weight. Per-factor `fetched_at` / `ingested_at` / `source_updated_at` (oldest wins) drives the multiplier. UI: hover shows freshness per factor; polygon corner badge when any factor is currently dropped; §9.7 dim 1 verdict prepends staleness disclaimer when cost factors are past budget. Open work flagged in this changelog → §11 / future migrations: many of these factors need new fetchers (LEHD LODES, Building Permits, HUD subsidized housing, ACS B25002 / B19013 / B25003 multi-vintage).
- 2026-04-26 — Specced four new pipeline sources to unlock §9.3.2 factors. §13.21 Chicago Building Permits (Socrata `ydr8-5enu`, new `building_permits` table — drives the construction-pipeline macro factor). §13.22 ACS extended variables `B19013 / B25002 / B25003` (extends existing fetcher; adds `tracts.income_median`, `vacancy_rate`, `owner_occupied_pct`, `renter_occupied_pct` — drives 4 macro factors in one shot with pop-weighted CCA rollup rules pinned). §13.23 Chicago Parking Lots (Socrata `94t9-w7tc`, new `parking_lots` table — replaces blocked SpotHero, drives parking-cost micro factor). §13.24 CPS Attendance Boundaries (Socrata `8wkm-z37x`, new `school_boundaries` table — switches `school_elem` from nearest-school to point-in-polygon containment, jumping confidence 7→9). New rows added to §6.1 status table. §13.26 sketches migration `012_color_factor_sources.sql` (per no-bloat rule, not written until first fetcher of the four is being implemented). Old §13.19 ("why columns predate 001") renumbered to §13.25.
- 2026-04-26 — Built the four new sources at parity with existing pattern: migration `012_color_factor_sources.sql` (3 tables + 5 tracts columns + indexes), `scripts/fetchers/fetch_building_permits.py`, `fetch_parking_lots.py`, `fetch_school_boundaries.py`, plus matching transformers and `SILVER_TABLE` registry rows. ACS fetcher rewritten in place to pull all 10 §13.22 variables in one Census API call, with sentinel handling and ratio derivation; added `to_silver()` and `run(run_id)` so it matches the fetcher contract.
- 2026-04-26 — Added §15 Data integrity & ACID contract + migration `013_data_integrity_constraints.sql` + `scripts/utils/validation.py`. Postgres-side: NOT-NULL + CHECK constraints on `buildings`, `cpd_incidents`, `complaints_311`, `tracts`, `building_permits`, `parking_lots` (Chicago bbox via shared `in_chicago_bbox()` SQL fn, range checks on ratios, non-negativity on costs/counts, `year_built` sanity range). All CHECKs `NOT VALID` so existing rows aren't scanned. Loader-side: `acquire_source_lock` (advisory lock per source), `assert_failure_rate` (bronze→silver drop ≤ 10%), `assert_row_count_drift` (silver count drop ≤ 50% vs last successful run). All three wired into `load_all()` so they have current callers. Verification step #13 checks the loader still calls them.
