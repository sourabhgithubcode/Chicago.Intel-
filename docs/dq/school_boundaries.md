# school_boundaries — DQ Audit

**Date:** 2026-05-27
**Source:** Chicago Data Portal `5ihw-cbdn` — CPS Elementary Attendance Boundaries SY2425
**Fetcher:** `scripts/fetchers/fetch_cps_elementary_boundaries.py`
**Transformer:** `scripts/transformers/cps_boundaries.py`
**Schema:** not in `001`/`013` (table created out-of-band; no CHECK constraints declared in migrations)
**Mode:** Read-only

## Summary

353 rows, stable vs prior audit. All elementary (`grade_category='ES'`) — no middle/high school boundaries loaded. `school_id` and `school_name` both 100% distinct; geometry 100% MultiPolygon/EPSG:4326 within Chicago bbox. `rcdts` is 100% NULL by design (transformer hardcodes None). No freshness columns on the table. Production-usable as elementary attendance layer; gap is that the SY2425 dataset is the only one represented and there is no audit trail of when it was loaded.

## Row count

| Metric | Value |
|---|---|
| Current rows | 353 |
| Prior audit (2026-05-15) | 353 |
| Drift | 0 |

## NULL

| Column | NULLs | % |
|---|---|---|
| school_id | 0 | 0.00% |
| rcdts | 353 | 100.00% |
| school_name | 0 | 0.00% |
| grade_category | 0 | 0.00% |
| school_year | 0 | 0.00% |
| boundary | 0 | 0.00% |

`rcdts` NULL-by-design — transformer line 31 hardcodes `None` (placeholder column, no source mapping). Either drop the column or wire it from a CPS roster source.

## Constraint

| Check | Result |
|---|---|
| PK `school_id` distinct | 353 / 353 |
| `school_name` distinct | 353 / 353 |
| Migration 013 constraints on `school_boundaries` | none (grep → no matches) |
| Geometry type uniformity | MultiPolygon × 353 |
| SRID | 4326 (set in transformer via `SRID=4326;…` WKT prefix) |

No CHECK constraints declared in any migration. Table appears to have been created out-of-band — not present in `001_create_tables.sql`, `013_data_integrity_constraints.sql`, or any subsequent migration.

## Geometry

| Metric | Value |
|---|---|
| NULL boundary | 0 / 353 |
| Geometry type | MultiPolygon × 353 |
| Lon bbox | [-87.86193, -87.52414] |
| Lat bbox | [41.64454, 42.02304] |
| Chicago bbox check (lon -87.94..-87.52, lat 41.64..42.02) | 0/107,330 lon-out, 92/107,330 lat-out (0.086%) |
| Vertex count (all polygons) | 107,330 |

92 vertices marginally above lat 42.02 — within normal MultiPolygon edge tolerance for far-north schools (Edison Park / Rogers Park area); not a data error.

## School distribution

| Field | Distribution |
|---|---|
| `grade_category` | `ES`: 353 (100%) |
| `school_year` distinct values | 6 |
| `school_year` top | `K, 1, 2, 3, 4, 5, 6, 7, 8`: 329 |
|  | `K, 1, 2, 3, 4, 5, 6`: 10 |
|  | `K, 1, 2, 3, 4, 5`: 8 |
|  | `K, 1, 2, 3, 4`: 4 |
|  | `K, 1, 2`: 1 |
|  | (1 other) | |

Only elementary boundaries — no MS/HS coverage in this table. The fetcher's docstring confirms this is the SY2425 elementary edition only.

## Freshness

No `updated_at` / `created_at` / `ingested_at` / `load_ts` / `snapshot_date` column on the table. Load timestamp is not recoverable from the table itself; would need to consult `pipeline_runs` if a `cps_boundaries` run was recorded.

## Drift

None vs 2026-05-15. Row count, geometry type uniformity, distinct school IDs, and grade_category distribution all unchanged.

## Recommendation

- **Schema debt:** add a migration to formally declare the table (`school_id TEXT PRIMARY KEY`, `boundary geometry(MultiPolygon, 4326) NOT NULL`, GIST index) and a CHECK on bbox. Currently the table exists but has no declarative source-of-truth in `supabase/migrations/`.
- **`rcdts` column:** remove it (no caller, 100% NULL, transformer hardcodes None) unless a CPS roster join is planned in the next change.
- **Coverage gap:** if downstream needs HS/MS boundaries, fetch the corresponding CPS datasets and add `grade_category` discrimination — currently a `school_elem` lookup is the only thing supported.
- **No freshness column:** if quarterly refresh matters, add `ingested_at TIMESTAMPTZ DEFAULT NOW()` when formalizing the schema.
- Safe to use for point-in-polygon assignment of `school_elem` in `buildings` enrichment (confidence 9/10 per fetcher docstring).
