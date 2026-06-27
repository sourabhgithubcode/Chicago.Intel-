# Silver Layer — Data Completeness Scorecard

**Generated:** 2026-05-30
**Basis:** per-table DQ audits in `docs/dq/*.md` (2026-05-27) + verified source-cadence fact-check (2026-05-30)
**Tables:** 15 silver tables

> **Completeness ≠ cleanliness.** This scorecard measures *how much of the intended data is actually present and current*, not whether the rows that exist are valid. A table can be 100% clean (no bad rows) and still incomplete (missing columns, stale, or never-fetched row categories).

## Method & honesty caveats

- **Row completeness is INFERRED, not proven.** No fetcher computes a source `count(*)` today, so we cannot assert "we got every row the API has." The only completeness control we have is row-count stability between audits. Building the `pipeline_runs` reconciliation (source vs fetched vs loaded counts) is the prerequisite for *proving* any of these numbers.
- **Freshness is judged against the VERIFIED publisher cadence**, which corrected several CLAUDE.md assumptions (CPD is daily not annual; Assessor is monthly not annual; ACS 2019–23 is superseded by 2020–24; several GIS layers are effectively frozen).
- Scores are a single-analyst estimate per table; treat as directional.

## Gap taxonomy

| Tag | Meaning | Fix path |
|---|---|---|
| `[SOURCE-EMPTY]` | Upstream genuinely has nothing | None — document as expected |
| `[PIPELINE-NOT-RUN]` | Data is gettable; reconcile/enrichment/scoring/fetch never ran | Run the job |
| `[BY-DESIGN]` | Intentionally not materialized | None — or remove dead columns |
| `[STALE-VINTAGE]` | A newer source release exists | Re-fetch newer vintage |
| `[SOURCE-STATIC]` | The source itself is frozen | None — re-fetch is pointless |

---

## Master scorecard

| Table | Rows | Cols full | Completeness | Dominant gap |
|---|---:|---|---:|---|
| `parks` | 614 | 5 / 5 | **100%** | source static (no deficiency) |
| `winter_overnight_restrictions` | 20 | 6 / 6 | **100%** | source static |
| `snow_route_restrictions` | 144 | 4 / 6 | **99%** | 1 park-loop endpoint |
| `building_footprints` | 820,598 | 2 / 2 | **98%** | `bldg_id=0` sentinel |
| `displacement_typology` | 1,982 | 2 / 2 | **95%** | 45 Chicago tracts missing (vintage) |
| `cpd_incidents` | 1,471,413 | 6 / 6 | **90%** | ~28d stale vs daily source |
| `building_permits` | 226,114 | 6 / 11 | **80%** | 75% "other" + ~20d stale |
| `parking_permit_zones` | 10,372 | 7 / 10 | **80%** | 163 invalid wards + daily-stale |
| `cta_stops` | 10,833 | 4 / 5 | **78%** | `lines` never fetched |
| `streets` | 55,872 | 6 / 8 | **73%** | `cca_id`/`tract_id` reconcile not run |
| `ccas` | 77 | 8 / 11 | **70%** | 3 score cols never computed |
| `school_boundaries` | 353 | 5 / 6 | **65%** | MS/HS not fetched |
| `complaints_311` | 454,227 | 5 / 6 | **60%** | `address_norm` empty + narrow type filter |
| `tracts` | 1,348 | 6 / 17 | **50%** | 41% no geometry/CCA + scores + stale vintage |
| `buildings` | 858,157 | 7 / 23 | **45%** | 10 empty cols + 3 silent-zero |

**Unweighted mean ≈ 79%**, but that flatters reality: the two tables that matter most to the building-view product — `buildings` (45%) and `tracts` (50%) — are the least complete. A product-weighted score would be materially lower.

---

## Per-table detail

### buildings
- **Rows:** 858,157 (unchanged since 2026-05-15)
- **Row completeness:** No entire row-categories appear missing — `pin` PK clean (858,157 distinct), core identity columns 0% NULL. Inferred only; no source `count(*)` reconciliation against Cook County Assessor.
- **Column completeness:** 7 of 23 fully populated (`pin`, `address`, `address_norm`, `owner`, `school_elem` ~99.96%, `location`, `updated_at`). Partial: `year_built` 51.6% NULL, `purchase_year`/`purchase_price` 51.2% NULL. Silent-zero (INT DEFAULT 0, enrichment never ran): `violations_5yr`, `heat_complaints`, `bug_reports`. 100%-empty (10): `tax_current`, `tax_annual`, `landlord_score`, `flood_zone`, `street_id`, `flood_zone_at`, `rent_estimate`, `rent_estimate_at`, `school_rating`, `school_rating_at`.
- **Freshness:** Stale — `max(updated_at)` 2026-05-15, no change since last bronze load. Source updates monthly; tax fields sourced separately (Treasurer) and never fetched.
- **Gap classification:**
  - `year_built`/`purchase_*` ~51% NULL — `[SOURCE-EMPTY]` (assessor records only arm's-length sales / lacks build year for many parcels)
  - `tax_current`/`tax_annual` — `[PIPELINE-NOT-RUN]` (Treasurer enrichment from cookcountytreasurer.com never ran)
  - `violations_5yr`/`heat_complaints`/`bug_reports` all `0` — `[PIPELINE-NOT-RUN]` (311→buildings spatial join never ran)
  - `street_id` — `[PIPELINE-NOT-RUN]` (reconcile never ran)
  - `flood_zone` — `[PIPELINE-NOT-RUN]` (FEMA batch never ran; note product design is live-per-query)
  - `landlord_score` — `[PIPELINE-NOT-RUN]` (scoring never ran)
  - `flood_zone_at`/`rent_estimate`/`rent_estimate_at`/`school_rating`/`school_rating_at` — `[BY-DESIGN]` placeholder columns shipped with no writer (removal candidates per no-bloat rule)
- **Completeness score:** **~45%.** Identity/location solid, but every column that drives building-view intelligence (tax, violations, flood, landlord, street linkage) is unpopulated and waiting on jobs that never ran.

### cpd_incidents
- **Rows:** 1,471,413
- **Row completeness:** No missing categories; all 6 columns 0% NULL, every row type-classified, 2020-01-01 → 2026-05-02. Inferred — no source `count(*)`.
- **Column completeness:** 6 / 6 fully populated. (`type='other'` 55.9% is a classification concern, not a completeness gap.)
- **Freshness:** Stale-by-~28-days; no new rows in 12+ days. Source updates **daily**, so the fetcher simply hasn't run.
- **Gap classification:**
  - 28-day lag — `[PIPELINE-NOT-RUN]` (daily source, fetcher hasn't run)
  - 6.3-yr load vs 5-yr spec — `[BY-DESIGN]` ambiguity (extra rows present, not missing)
- **Completeness score:** **~90%.** Structurally complete; only deduction is ~4 weeks of recent incidents not yet loaded.

### complaints_311
- **Rows:** 454,227
- **Row completeness:** Entire categories missing — only 2 `sr_type`s loaded (Rodent 318,358; Building Violation 135,869); other types (e.g. Sanitation Code Violation) absent from the fetch filter. Heat & bed-bug are NOT separate types — they roll into Building Violation (already have them), so NOT a missing fetch.
- **Column completeness:** 5 / 6 fully populated (`address` 22 NULL ≈ 0%). 100%-empty: `address_norm` (transformer never computes it; migration 005 index unused).
- **Freshness:** Stale-by-~21-days. Source updates multiple times/day.
- **Gap classification:**
  - `address_norm` — `[PIPELINE-NOT-RUN]` (one-pass normalizer backfill)
  - Missing sr_types beyond the 2 loaded — `[PIPELINE-NOT-RUN]` (widen `fetch_311.py` filter)
  - ~21-day staleness — `[PIPELINE-NOT-RUN]`
- **Completeness score:** **~60%.** Geometry/dates/identity clean, but one full column empty and only 2 of the intended complaint types fetched.

### tracts
- **Rows:** 1,348
- **Row completeness:** All 1,348 ACS tracts present, but two row-category gaps: 547 (40.6%) NULL `geometry` (TIGER vintage mismatch), 563 (41.8%) lack `cca_id` (reconcile partial — 785 mapped).
- **Column completeness:** 6 / 17 fully populated. Partial: `cca_id` 41.8%, `geometry` 40.6%, `rent_median` 4.5%, `income_median` 2.3%, `population`/`*_moe` ~1.2%, occupancy ~1.5% NULL. Contamination: 52 `rent_moe` + 25 `income_moe` rows carry raw Census `-333333333` sentinel; 10 `income_median` top-coded $250,001. 100%-empty (4): `name`, `safety_score`, `walk_score`, `disp_score`.
- **Freshness:** **Superseded-vintage** — all rows `2019-23`; ACS 2020-24 shipped Dec 2025.
- **Gap classification:**
  - `2019-23` vintage — `[STALE-VINTAGE]`
  - `geometry` 40.6% NULL — `[PIPELINE-NOT-RUN]` (TIGER 2020 refetch)
  - `cca_id` 41.8% NULL — `[PIPELINE-NOT-RUN]` (reconcile partial)
  - `name` — `[PIPELINE-NOT-RUN]` (no tracts transformer; ACS NAME available)
  - `safety_score`/`walk_score`/`disp_score` — `[PIPELINE-NOT-RUN]` (scoring never ran)
  - `*_moe` sentinels — `[PIPELINE-NOT-RUN]` (map to NULL in transformer; 1-line backfill)
  - `rent_median`/`income_median`/`population` ~1–4% NULL — `[SOURCE-EMPTY]` (ACS suppresses small denominators)
- **Completeness score:** **~50%.** ACS measures largely present, but ~41% of rows can't render/roll-up (no geometry/CCA), all scores + `name` empty, vintage superseded, sentinels uncleaned.

### building_permits
- **Rows:** 226,114
- **Row completeness:** Inferred (delta 0 vs prior). Daily source, data ends 2026-05-10 → ~18 days of permits absent.
- **Column completeness:** 6 / 11 fully populated. Partial: `applied_at` 0.01%, `address`/`address_norm` 0.001%, `reported_cost` 5.65%, `location` 1.82% NULL. 100%-empty: `pin`. No `status` column.
- **Freshness:** Stale-by-~20-days vs a **daily** source.
- **Gap classification:**
  - `pin` — `[SOURCE-EMPTY]`
  - `category='other'` 75.4% — `[PIPELINE-NOT-RUN]` (transformer classification gap)
  - no `status` column — `[BY-DESIGN]`
  - ~18d of permits absent — `[STALE-VINTAGE]`
- **Completeness score:** **~80%.** Most columns populated and rows clean; daily-source staleness + 75% unclassified "other" dent currency and usability.

### building_footprints
- **Rows:** 820,598
- **Row completeness:** Inferred (delta 0; prior 8-row dedupe accounted for). Source static, so no missing categories expected.
- **Column completeness:** 2 / 2 fully populated (all MultiPolygon EPSG:4326 in bbox). Minimal schema; no migration defines the table.
- **Freshness:** Static (source untouched since 2015). No freshness column.
- **Gap classification:**
  - source unchanged since 2015 — `[SOURCE-STATIC]`
  - only `bldg_id`+`geometry`; no declarative migration — `[BY-DESIGN]`
  - `bldg_id=0` sentinel-looking row — `[SOURCE-EMPTY]`
- **Completeness score:** **~98%.** Both columns 100% populated/clean; only deductions are the unresolved sentinel and no schema/freshness guarantee.

### streets
- **Rows:** 55,872
- **Row completeness:** Inferred (delta 0, PK clean). Source static (~2016).
- **Column completeness:** 6 / 8 fully populated. 100%-empty: `cca_id`, `tract_id`. Geometry-type drift (live LineString vs declared MultiLineString) is a schema-contract issue, not completeness.
- **Freshness:** Static.
- **Gap classification:**
  - `cca_id`/`tract_id` — `[PIPELINE-NOT-RUN]` (in-DB `assign_streets_to_polygons()` never ran; CCA half now unblocked since `ccas.geometry` populated)
  - source unchanged since ~2016 — `[SOURCE-STATIC]`
- **Completeness score:** **~73%.** All source columns populated; the two derived spatial keys empty (recoverable via in-DB join).

### cta_stops
- **Rows:** 10,833
- **Row completeness:** Inferred (delta 0, PK clean). Suburban stops dropped by bbox filter (by design).
- **Column completeness:** 4 / 5 fully populated. 100%-empty: `lines` (`[]` on all rows). `accessible` populated but suspect (99.1% true vs CTA's published ~70%).
- **Freshness:** Effectively static for purpose (coords rarely move) though GTFS refreshes ~every 3–4 weeks.
- **Gap classification:**
  - `lines` empty — `[PIPELINE-NOT-RUN]` (`stop_times`/`trips`/`routes` never fetched; only `stops.txt`)
  - suburban stops dropped — `[BY-DESIGN]`
  - `accessible` likely GTFS default inflation — `[SOURCE-EMPTY]` (meaningful value not emitted per-stop)
- **Completeness score:** **~78%.** Location data complete/current; `lines` 100% empty blocks transit-line filtering.

### ccas
- **Rows:** 77
- **Row completeness:** All 77 CCAs present (fixed universe). Geometry now populated (resolved since prior audit).
- **Column completeness:** 8 / 11 fully populated. 100%-empty: `walk_score`, `run_score`, `vibe_score`.
- **Freshness:** Mixed — geometry static/current; `rent_median` is `2019-23`, superseded by ACS 2020-24.
- **Gap classification:**
  - `walk_score`/`run_score`/`vibe_score` — `[PIPELINE-NOT-RUN]` (scoring never ran)
  - `rent_median` vintage — `[STALE-VINTAGE]`
  - geometry source "as needed" — `[SOURCE-STATIC]`
- **Completeness score:** **~70%.** All rows + core scores present, geometry resolved; 3 of 11 columns unbuilt and rent on a superseded vintage.

### parks
- **Rows:** 614
- **Row completeness:** All ~614 features present (delta 0). Inferred against documented feature count.
- **Column completeness:** 5 / 5 fully populated, 0 NULLs, 614 distinct names.
- **Freshness:** Static (source frozen ~2016, last touch 2022); zero drift matches.
- **Gap classification:** source effectively frozen — `[SOURCE-STATIC]`
- **Completeness score:** **100%.** Every row and column populated, zero issues; only "gap" is the static source.

### school_boundaries
- **Rows:** 353
- **Row completeness:** All 353 ES rows present, but only SY2425 **elementary** loaded — MS/HS NOT fetched (coverage decision).
- **Column completeness:** 5 / 6 fully populated. 100%-empty: `rcdts` (hardcoded None).
- **Freshness:** Current for what's loaded (SY2425 latest), annual source.
- **Gap classification:**
  - MS/HS boundaries not fetched — `[BY-DESIGN]`
  - `rcdts` — `[BY-DESIGN]` placeholder
- **Completeness score:** **~65%.** ES layer complete/current, but two of three school levels absent by decision.

### displacement_typology
- **Rows:** 1,982
- **Row completeness:** All 1,982 present (delta 0). 679 suburban geoids = expected (UDP covers full CMAP region). 45 Chicago tracts have no typology row (96.7% coverage) — a true source-vintage gap.
- **Column completeness:** 2 / 2 fully populated, 11 categories.
- **Freshness:** Frozen (UDP 2000–2017; IHS last Feb 2022). Re-fetch yields nothing new.
- **Gap classification:**
  - source frozen — `[SOURCE-STATIC]`
  - 45 Chicago tracts missing — `[SOURCE-EMPTY]` (vintage predates current ACS tract set)
  - 679 suburban geoids — `[BY-DESIGN]` (not a gap)
- **Completeness score:** **~95%.** Both columns clean against a frozen source; only shortfall is 45 Chicago tracts (3.3%).

> **Naming caveat:** the typology labels here ("Advanced Gentrification", "At Risk of Becoming Exclusive") are **Urban Displacement Project** labels (2000–2017 static), not the DePaul IHS three-tier framing. If this field is meant to mirror IHS, they are not interchangeable.

### parking_permit_zones
- **Rows:** 10,372
- **Row completeness:** Likely complete (95.22% ACTIVE, side balance plausible). Inferred — no source `count(*)`.
- **Column completeness:** 7 / 10 fully populated. Partial: `street_type` 99.39% (63 NULL), `ward` 99.80% (21 NULL) — plus 142 `ward=0` sentinels = 163 (1.57%) invalid wards.
- **Freshness:** Stale ~18 days vs a **daily** source.
- **Gap classification:**
  - frozen at 2026-05-12 vs daily source — `[STALE-VINTAGE]`
  - 142 `ward=0` (zones 1676/2438) — `[SOURCE-EMPTY]` (source-side gap)
  - 21 `ward=NULL` — `[SOURCE-EMPTY]` (combined 163; prior rollup miscounted as 21, a 7× understatement)
  - 63 `street_type` NULL + 13 zero-address — `[SOURCE-EMPTY]` (minor)
- **Completeness score:** **~80%.** Near-fully populated, but daily-staleness + 163 invalid wards drag it down.

### snow_route_restrictions
- **Rows:** 144
- **Row completeness:** Plausibly complete for the 2-inch slice (IDs 1–165; 21 missing belong to the sibling overnight table from the shared feed). Inferred.
- **Column completeness:** 4 / 6 fully populated. Partial: `from_street`/`to_street` 99.31% (1 NULL — `id=153 WASHINGTON PARK`).
- **Freshness:** Static (one-off 2021 snapshot).
- **Gap classification:**
  - one-off 2021 snapshot — `[SOURCE-STATIC]`
  - uniform `restriction_type='2 INCH'` — `[BY-DESIGN]`
  - 1 park-loop row missing endpoints — `[SOURCE-EMPTY]`
  - 21 non-contiguous IDs — `[BY-DESIGN]` (belong to overnight table)
- **Completeness score:** **~99%.** Fully populated and internally consistent; only the single park-loop endpoint gap.

### winter_overnight_restrictions
- **Rows:** 20
- **Row completeness:** Plausibly complete (sparse 45–138 subset of shared id space). Inferred.
- **Column completeness:** 6 / 6 fully populated, 0 NULLs.
- **Freshness:** Static (one-off 2021 snapshot).
- **Gap classification:**
  - one-off 2021 extract — `[SOURCE-STATIC]`
  - uniform `restriction_type='OVERNIGHT'` — `[BY-DESIGN]`
  - 4 `on_street` missing N/S/E/W prefix — `[BY-DESIGN]` (cosmetic)
- **Completeness score:** **100%.** All columns populated, geometry valid; only a cosmetic prefix note.

---

## What would move the numbers

Grouped by fix path, highest product impact first:

1. **Run reconcile** (in-DB, no API) → fills `buildings.street_id`, `streets.cca_id`/`tract_id`, finishes `tracts.cca_id`. Lifts buildings, streets, tracts.
2. **Run enrichment fetchers** → Treasurer tax (buildings), CTA routes join (`cta_stops.lines`), TIGER 2020 (`tracts.geometry`), widen `fetch_311.py` types.
3. **Run scorers** → `tracts` safety/walk/disp, `ccas` walk/run/vibe.
4. **Re-fetch for freshness** → CPD (daily), 311 (daily), permits (daily), parking zones (daily) are all ~3–4 weeks stale.
5. **Re-fetch newer vintage** → ACS 2020–24 (supersedes 2019–23 in `tracts` + `ccas`).
6. **Backfill transformers** → `complaints_311.address_norm`, `tracts` Census sentinels → NULL, building_permits category expansion.
7. **Decide / drop** → 5 placeholder building columns, `tracts.name`, `school_boundaries.rcdts` — remove or wire writers (no-bloat).
8. **No action** → parks, snow/winter restrictions, displacement_typology, building_footprints, streets geometry: sources are static/frozen.

**Blocked by the data-load freeze** (`project_data_load_freeze.md`): items 1–6 should not run until transformer cleaning is validated per source. The single highest-leverage *unblocked* task is building the `pipeline_runs` source-count reconciliation — read-only verification infrastructure that turns every "inferred" row-completeness above into a *proven* number.
