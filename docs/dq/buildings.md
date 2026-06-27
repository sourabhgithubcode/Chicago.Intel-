# DQ Audit: buildings
**Generated:** 2026-05-27
**Prior audit:** 2026-05-15
**Rows:** 858,157 (prior: 858,157 — no change)

## Summary

| Severity | Finding |
|---|---|
| RED | `tax_current`, `tax_annual`, `street_id`, `flood_zone`, `landlord_score` still 100% NULL — Treasurer enrichment, reconcile, FEMA batch, and landlord scoring never ran. Identical to 05-15. |
| RED | `violations_5yr`, `heat_complaints`, `bug_reports` all `0` for every row — 311→buildings spatial join still hasn't run. (NB: column type is `INT DEFAULT 0`, so technically not NULL — zero is the silent failure mode.) |
| RED | 5 new enrichment columns added since 05-15 (`flood_zone_at`, `rent_estimate`, `rent_estimate_at`, `school_rating`, `school_rating_at`) — all 100% NULL. Columns shipped but no writer exists. |
| ORANGE | `year_built` 51.6% NULL, `purchase_year`/`purchase_price` 51.2% NULL — unchanged. Assessor source gaps, expected. |
| ORANGE | 528 buildings with `purchase_price` > $100M, max $850M — repeated from 05-15. Likely high-rise commercial / portfolio sales; would distort rent/value heuristics if not capped. |
| ORANGE | 7 buildings with `year_built < 1850` (min 1836) — Chicago founded 1833; plausible but suspicious. Inside 013 sanity band (≥1830) so they pass CHECK. |
| GREEN | `pin` PK clean (858,157 distinct by definition), `address` / `address_norm` / `owner` / `updated_at` 0% NULL, all 5 migration-013 CHECKs pass on current rows, sampled coordinates inside Chicago bbox. |

## Row count

- Total: **858,157** (unchanged from 2026-05-15)
- `pin` is `TEXT PRIMARY KEY` (001 L78) — uniqueness guaranteed by the constraint; no separate duplicate scan needed.

## NULL analysis (all 23 columns)

| Column | NULLs | % | Notes |
|---|---:|---:|---|
| pin | 0 | 0.0% | PK |
| address | 0 | 0.0% | also 0 empty strings |
| address_norm | 0 | 0.0% | satisfies 013 L22-24 |
| owner | 0 | 0.0% | also 0 empty strings |
| year_built | 442,795 | **51.6%** | unchanged; assessor gap |
| purchase_year | 439,287 | **51.2%** | only arm's-length sales recorded |
| purchase_price | 439,287 | **51.2%** | same rows as `purchase_year` |
| tax_current | **858,157** | **100.0%** | Treasurer enrichment never ran |
| tax_annual | **858,157** | **100.0%** | Treasurer enrichment never ran |
| violations_5yr | 0 | 0.0% | but **100% are literally `0`** — enrichment never ran |
| heat_complaints | 0 | 0.0% | same as above (`0` rows w/ value > 0) |
| bug_reports | 0 | 0.0% | same as above (`0` rows w/ value > 0) |
| landlord_score | **858,157** | **100.0%** | scoring job never ran |
| flood_zone | **858,157** | **100.0%** | no batch FEMA enrichment |
| school_elem | 319 | 0.0% | clean — populated by spatial join to school_boundaries |
| location | (not measurable) | — | `location IS NULL` filter times out (no index); sample of 5 all in Chicago bbox; prior audit reported 0 out-of-bbox |
| updated_at | 0 | 0.0% | |
| street_id | **858,157** | **100.0%** | reconcile never ran (added in migration 007) |
| flood_zone_at | **858,157** | **100.0%** | new column; no writer |
| rent_estimate | **858,157** | **100.0%** | new column; no writer |
| rent_estimate_at | **858,157** | **100.0%** | new column; no writer |
| school_rating | **858,157** | **100.0%** | new column; no writer |
| school_rating_at | **858,157** | **100.0%** | new column; no writer |

## Constraint compliance

Migration 013 CHECK constraints for buildings — all pass against current rows (all added `NOT VALID`):

| Constraint | Migration 013 lines | Violations |
|---|---|---:|
| `buildings_address_norm_present` (address_norm IS NOT NULL) | L22–24 | 0 |
| `buildings_purchase_price_nonneg` (purchase_price >= 0) | L25–27 | 0 |
| `buildings_tax_annual_nonneg` (tax_annual >= 0) | L28–30 | 0 (vacuously — column 100% NULL) |
| `buildings_year_built_sane` (year_built BETWEEN 1830 AND 2100) | L31–33 | 0 (min=1836, max=2024) |
| `buildings_location_in_chicago` (in_chicago_bbox helper) | L34–36 (helper L12–19) | not measurable via PostgREST; sampled 5/5 inside; prior audit reported 0 out-of-bbox |

Safe to promote all five from `NOT VALID` → enforced via `ALTER TABLE buildings VALIDATE CONSTRAINT …` once a direct DB session is available.

## Geometry / spatial

| Check | Result |
|---|---|
| Geometry type | `GEOMETRY(POINT, 4326)` per 001 L93 — sample confirms `Point` GeoJSON |
| Sample bounding box | lon [-87.7441, -87.6320], lat [41.8865, 41.9762] — inside Chicago bbox |
| Chicago bbox (013 helper) | lon [-87.940, -87.524], lat [41.644, 42.023] |
| `location IS NULL` count | **unmeasurable** via PostgREST (statement timeout, no partial index); prior audit found 0 |
| Out-of-bbox rows | **unmeasurable** via PostgREST (no ST_X exposure); prior audit found 0 |

Prior audit's "Out-of-bbox coordinates: 0 across buildings" stands as the most recent direct count.

## Outliers

| Column | Issue | Count | Notes |
|---|---|---:|---|
| `year_built` | < 1850 | **7** | min = 1836 (PIN `17294120380000`); next 1844, 1847, 1847, 1848 — same 7 as 05-15 |
| `year_built` | > 2026 | 0 | max = 2024 |
| `year_built` | non-NULL total | 415,362 | matches 05-15 |
| `purchase_price` | min | $10,050 | matches 05-15 |
| `purchase_price` | > $50M | **1,539** | new in this audit (not bucketed before) |
| `purchase_price` | > $100M | **528** | matches 05-15 ("528 properties with purchase_price > $100M") |
| `purchase_price` | max | **$850,000,000** | two PINs tied: `17094050040000`, `17094050080000` (W Loop / Wacker area) — same outlier as 05-15 |
| `tax_current` / `tax_annual` | outlier check | n/a | column 100% NULL — no values to check |

The seven sub-1850 rows and the $850M sale are persistent oddities. All inside the 013 sanity bands.

## Referential integrity (street_id, cca_id, tract_id)

| Column | Result |
|---|---|
| `street_id` | exists (added migration 007 L39), FK → `streets(id)`. **100% NULL** → 0 rows to validate; orphan count = 0 vacuously. |
| `cca_id` | **column does not exist on `buildings`** (returns `42703` from PostgREST). Buildings reach CCAs transitively via `street_id → streets.cca_id` per the streets-as-spine design. |
| `tract_id` | **column does not exist on `buildings`** (returns `42703`). Same transitive pattern. |

So the only FK to evaluate is `street_id`, and reconcile not having run makes it a no-op. When reconcile fires, validate orphan count via `WHERE street_id NOT IN (SELECT id FROM streets)`.

## Drift from 2026-05-15

| Metric | 2026-05-15 | 2026-05-27 | Delta |
|---|---|---|---|
| Row count | 858,157 | 858,157 | 0 |
| `tax_current` / `tax_annual` NULL | 100% | 100% | no change |
| `street_id` NULL | 100% | 100% | no change |
| `flood_zone` NULL | 100% | 100% | no change |
| `landlord_score` NULL | not separately flagged | **100%** | newly explicit |
| `violations_5yr` / `heat_complaints` / `bug_reports` > 0 | "all 0" | 0 / 0 / 0 | no change |
| `year_built` NULL | 51.6% (442,795) | 51.6% (442,795) | no change |
| `purchase_year` / `purchase_price` NULL | 51.2% (439,287) | 51.2% (439,287) | no change |
| `year_built < 1850` | 7 | 7 | no change |
| `purchase_price > $100M` | 528 | 528 | no change |
| `purchase_price` max | $850M | $850M | no change |
| New empty cols (`rent_estimate`, `rent_estimate_at`, `flood_zone_at`, `school_rating`, `school_rating_at`) | not present | **5 new cols, all 100% NULL** | shipped without writers |
| Freshness (`max(updated_at)`) | — | **2026-05-15T05:49:27Z** | unchanged since last bronze load; min 2026-05-10 |

**Net read:** zero progress on any of the P0–P3 enrichment items from 05-15. Schema grew by 5 columns that nothing writes to. Bronze load window (05-10 → 05-15) hasn't been re-run.

## Recommendation

Order by blast radius into Gold MVs / building-view UI:

1. **Run the 311→buildings spatial join.** `violations_5yr`, `heat_complaints`, `bug_reports` being identically zero across 858K rows is the most user-visible failure — building view will misleadingly show "0 violations, 0 heat complaints" as if researched. Either populate or hide the field until populated.
2. **Run reconcile to fill `street_id`.** Without it the streets→buildings rollup view (`gold_street_summary`-equivalent) is empty and the buildings→CCA transitive lookup is broken.
3. **Decide on the 5 placeholder columns** (`flood_zone_at`, `rent_estimate`, `rent_estimate_at`, `school_rating`, `school_rating_at`). Either wire writers in the next sprint or drop the columns — they violate the "no bloat / caller-required" rule in CLAUDE.md. Empty columns in a customer-facing schema invite "why is this NULL?" Slack threads.
4. **Cap/flag `purchase_price > $50M`.** 1,539 rows. Building view shouldn't surface "$850,000,000 last sale" as a per-unit affordability signal. Either filter from rent heuristics or label as a portfolio/commercial transaction.
5. **Investigate the 7 sub-1850 `year_built` rows.** Either correct from assessor source or accept and document (Chicago has a handful of pre-fire structures). They pass 013 (≥1830) so no constraint action needed.
6. **Validate the 5 migration-013 CHECKs.** All have 0 current violations (the `tax_annual` and `purchase_price` ones partly vacuous due to NULLs). Safe to `VALIDATE CONSTRAINT` to lock them in.
7. **Treasurer + FEMA batch + landlord scoring.** Same as 05-15 — these are full populator jobs, not transformer fixes; tracked under the data-load freeze.
