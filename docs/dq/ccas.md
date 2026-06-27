# DQ Audit: ccas
**Generated:** 2026-05-27
**Prior audit:** 2026-05-15
**Rows:** 77 (prior: 77)

## Summary
Geometry now 100% populated (resolved from prior 100% NULL); three score columns (`walk_score`, `run_score`, `vibe_score`) remain 100% NULL — never computed.

## Row count
- Current: 77
- Prior: 77
- Delta: 0 (matches authoritative count of Chicago Community Areas)

## NULL analysis
| Column | NULL % | Prior % | Note |
|---|---|---|---|
| id | 0.0% | 0% | PK |
| name | 0.0% | 0% | — |
| rent_median | 0.0% | 0% | ACS B25064 |
| safety_score | 0.0% | 0% | populated |
| walk_score | **100.0%** | n/a | never computed |
| run_score | **100.0%** | n/a | never computed |
| vibe_score | **100.0%** | n/a | never computed |
| disp_score | 0.0% | 0% | populated |
| geometry | **0.0%** | 100% | **resolved since prior audit** |
| data_vintage | 0.0% | 0% | all `'2019-23'` |
| updated_at | 0.0% | 0% | single timestamp 2026-04-24 |

## Constraint compliance
- Migration 013 defines **no** CHECK or NOT NULL constraints for `ccas` (grep confirms zero matches).
- Migration 001 (lines 8–20): `id` PRIMARY KEY ✓ (77/77 unique), `name NOT NULL` ✓ (0 nulls), `geometry GEOMETRY(MULTIPOLYGON, 4326)` ✓ (all rows MultiPolygon, CRS EPSG:4326).
- N/A: no numeric-range CHECKs to validate against.

## Geometry / spatial
| Check | Result |
|---|---|
| NULL geometry | 0 / 77 |
| Type = MultiPolygon | 77 / 77 |
| CRS | EPSG:4326 on all rows |
| Total vertices | 52,641 |
| Vertices outside Chicago bbox (lon −87.95 to −87.50, lat 41.63 to 42.05) | 0 / 52,641 |

## Outliers (numeric columns)
| Column | n | min | max | mean | Note |
|---|---|---|---|---|---|
| rent_median | 77 | $553 | $2,419 | $1,302 | plausible ACS B25064 range |
| safety_score | 77 | 0.00 | 9.85 | 7.66 | min=0.00 worth verifying (1 CCA at floor) |
| walk_score | 0 | — | — | — | all NULL |
| run_score | 0 | — | — | — | all NULL |
| vibe_score | 0 | — | — | — | all NULL |
| disp_score | 77 | 3.25 | 9.20 | 6.68 | within expected 0–10 |

## Drift from 2026-05-15
| Change | Direction |
|---|---|
| `geometry` 100% NULL → 0% NULL | **resolved** (P1 action item closed) |
| 77 rows, ids 1–77 | unchanged |
| `walk_score`/`run_score`/`vibe_score` 100% NULL | **new finding** (not flagged in prior audit, which only listed `geometry` for ccas) |
| `updated_at` single value 2026-04-24 03:42 UTC | last write was the geometry backfill |

## Recommendation
- Investigate the lone `safety_score = 0.00` row (likely a divide-by-zero / no-incidents edge case, not a true zero).
- Decide whether `walk_score`, `run_score`, `vibe_score` are still on the roadmap; if yes, route to a scorer; if no, drop the columns in a future migration to stop them showing as 100% NULL in every audit.
- No CHECK constraints needed yet — adding ranges (e.g. `safety_score BETWEEN 0 AND 10`) would only matter when a scorer writes to the table.
