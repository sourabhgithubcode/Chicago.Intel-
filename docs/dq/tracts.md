# DQ Audit: tracts
**Generated:** 2026-05-27
**Prior audit:** 2026-05-15
**Rows:** 1,348 (prior: 1,348 — no change)

## Summary

| Severity | Finding |
|---|---|
| RED | `name` 100% NULL — no transformer ever populates it (no `scripts/transformers/tracts.py` exists). New finding vs 05-15. |
| RED | `safety_score`, `walk_score`, `disp_score` still 100% NULL — unchanged. Gold MVs still broken. |
| RED | `rent_moe` 52 rows / `income_moe` 25 rows carry Census `-333333333` sentinel — leaks into UI as huge negative numbers if not filtered. New finding. |
| ORANGE | `cca_id` 41.8% NULL (was 100%). Reconcile partially ran — 785/1,348 mapped. 16 tracts have geometry but no cca_id. |
| ORANGE | `geometry` still 40.6% NULL (547 rows). Identical gap to 05-15. The 547 NULL-geom rows are exactly the same set still missing cca_id. |
| GREEN | id PK clean, no duplicates, FK orphans = 0, all CHECK constraints pass, geometry type = MultiPolygon, geometry bbox inside Chicago. |

## Row count
- Total: **1,348** (unchanged from 2026-05-15)
- Distinct `id`: **1,348** — no duplicates

## NULL analysis (all 17 columns)

| Column | NULLs | % | Notes |
|---|---:|---:|---|
| id | 0 | 0.0% | PK |
| cca_id | 563 | **41.8%** | reconcile gap |
| name | **1,348** | **100.0%** | never populated — no transformer |
| rent_median | 60 | 4.5% | |
| rent_moe | 16 | 1.2% | + 52 rows hold sentinel `-333333333` (see Outliers) |
| safety_score | **1,348** | **100.0%** | score job never ran |
| walk_score | **1,348** | **100.0%** | score job never ran |
| population | 16 | 1.2% | |
| disp_score | **1,348** | **100.0%** | score job never ran |
| geometry | 547 | **40.6%** | TIGER vintage mismatch (see Geometry) |
| data_vintage | 0 | 0.0% | all `2019-23` |
| updated_at | 0 | 0.0% | |
| income_median | 31 | 2.3% | + 10 rows top-coded at 250001 |
| income_moe | 16 | 1.2% | + 25 rows hold sentinel `-333333333` |
| vacancy_rate | 20 | 1.5% | |
| owner_occupied_pct | 20 | 1.5% | |
| renter_occupied_pct | 20 | 1.5% | |

## Constraint compliance

Migration 013 CHECK constraints — all pass against current rows:

| Constraint | Violations |
|---|---:|
| `tracts_population_nonneg` | 0 |
| `tracts_vacancy_rate_range` (0..1) | 0 |
| `tracts_owner_pct_range` (0..1) | 0 |
| `tracts_renter_pct_range` (0..1) | 0 |

Note: 013 added these as `NOT VALID`, so they only enforce on new writes. Above counts are full-table scans — table is clean by these CHECKs.

## Geometry / spatial

| Check | Result |
|---|---|
| Total non-NULL geometries | 801 / 1,348 (59.4%) |
| Geometry type | MultiPolygon (PostGIS SRID 4326) — 100% conformant |
| Bounding box (lon, lat) | [-87.9402, -87.5237] x [41.6443, 42.0239] |
| Chicago bbox (013) | [-87.940, -87.524] x [41.644, 42.023] — within bounds |
| Tracts with first-vertex outside Chicago bbox | 0 |
| Non-MultiPolygon entries | 0 |

Geometry gap (547 NULL) is the same population already documented in 05-15 audit: ACS 2019-23 enumerates 1,348 tracts on 2020 TIGER geoids, but the `tract_geometry` bronze loader covered only 801 (likely 2010 TIGER subset). Identical 547-row gap two weeks later — no progress.

## Outliers

| Column | Issue | Count | Example |
|---|---|---:|---|
| `rent_moe` | Census MOE sentinel `-333333333` | **52** | `17031800600`, `17031801902`, `17031807800` |
| `income_moe` | Census MOE sentinel `-333333333` | **25** | |
| `population` | Zero-population tracts | 4 | `17031990000`, `17031980000`, `17031381700`, … (parks, airports, industrial — expected) |
| `income_median` | Top-coded at $250,001 | 10 | `17031800100`–`17031800300` (Gold Coast, Lincoln Park) |
| `rent_median` | Min $343 → Max $3,501 | — | Plausible range; no values < $300 |
| `rent_median` | NULL | 60 | tracts where ACS suppressed for small denominators |
| `vacancy_rate` | Max 0.46 (Englewood `17031681400`) | — | High but plausible |
| `owner_occupied_pct` + `renter_occupied_pct` | sums to 1.0 across all rows | OK | inverse pairs check out |

**Action needed:** the `-333333333` Census sentinel is being persisted raw. Either NULL it in the transformer or filter `rent_moe >= 0` / `income_moe >= 0` in any consumer. As-is, a UI that surfaces "MOE: $-333,333,333" would be a credibility hit.

## Referential integrity (FK to ccas)

| Check | Result |
|---|---:|
| `cca_id` NULL | 563 (41.8%) |
| `cca_id` populated | 785 (58.2%) |
| Distinct populated `cca_id` values | 77 |
| `ccas` total rows | 77 |
| Orphan `cca_id` (not in `ccas.id`) | **0** |

All 77 CCAs are represented. Coverage gap is purely a reconcile-not-run problem, not a referential issue.

## Drift from 2026-05-15

| Metric | 2026-05-15 | 2026-05-27 | Delta |
|---|---|---|---|
| Row count | 1,348 | 1,348 | 0 |
| `geometry` NULL | 547 (40.6%) | 547 (40.6%) | **no change** |
| `cca_id` NULL | 1,348 (100%) | 563 (41.8%) | **-785 (reconcile partially ran)** |
| `safety_score` NULL | 1,348 (100%) | 1,348 (100%) | no change |
| `walk_score` NULL | 1,348 (100%) | 1,348 (100%) | no change |
| `disp_score` NULL | 1,348 (100%) | 1,348 (100%) | no change |
| `name` NULL | not flagged | **1,348 (100%)** | new finding |
| `rent_moe` Census sentinel rows | not flagged | **52** | new finding |
| `income_moe` Census sentinel rows | not flagged | **25** | new finding |
| Freshness (`max(updated_at)`) | — | 2026-05-12T05:02:59Z | bronze load window |

**Net read:** one P0 partially executed (reconcile). Geometry gap, score gaps, and (newly visible) `name` + Census sentinel issues unchanged or undetected.

## Recommendation

Order matches blast radius into Gold MVs / UI:

1. **NULL the Census sentinels.** In the `fetch_acs` / tracts transformer, map `-333333333` → NULL for `rent_moe`, `income_moe` before insert. Backfill: `UPDATE tracts SET rent_moe = NULL WHERE rent_moe < 0;` (and same for income_moe). One line each; no migration needed.
2. **Populate `name`.** Either drop the column or join the ACS NAME field (transformer doesn't exist — `scripts/transformers/tracts.py` is missing). Cheapest path: derive `'Tract ' || substr(id, 6)` if no canonical source; otherwise pull from ACS geography metadata.
3. **Finish reconcile for the 16 orphan-by-cca-only rows.** Geometry exists, cca_id is NULL — the spatial join should have caught these. Investigate why (point-in-polygon edge cases against CCA boundaries?).
4. **Close the 547-tract geometry gap.** Same recommendation as 05-15 — refetch TIGER 2020 tract geometries. Two weeks of no progress here means the underlying fetcher (`tract_geometry.py`) needs scope re-checked or the issue is unowned.
5. **Score columns (safety/walk/disp).** Still 100% NULL. Scoring is downstream — fine to defer until upstream gaps closed, but Gold MVs cannot ship until then.
6. **Validate the 013 CHECKs.** All zero violations currently — safe to `ALTER TABLE tracts VALIDATE CONSTRAINT …` for the four tracts constraints, promoting them from `NOT VALID` to enforced.
