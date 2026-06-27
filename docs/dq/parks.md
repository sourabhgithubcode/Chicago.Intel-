# Silver DQ — `parks`

**Audited:** 2026-05-27 | **Source:** Chicago Park District ArcGIS (CW_414) | **Confidence:** 9/10

## Summary

Clean. 614 rows, zero nulls, zero PK dupes, zero geometry issues, zero drift vs 2026-05-15. No remediation needed.

## Row count

| Metric | Value |
|---|---|
| Current | 614 |
| 2026-05-15 baseline | 614 |
| Source-expected (~614 features) | match |

## NULL

| Column | NULLs | % |
|---|---|---|
| `id` | 0 | 0% |
| `name` | 0 | 0% |
| `acreage` | 0 | 0% |
| `location` | 0 | 0% |
| `boundary` | 0 | 0% |

Also: 0 empty-string names, 614 distinct names (no name collisions).

## Constraint

Schema (migration 001): `id INT PK, name TEXT NOT NULL, acreage NUMERIC(8,2), location GEOMETRY(POINT,4326), boundary GEOMETRY(MULTIPOLYGON,4326)`.

Migration 013 defines **no CHECK constraints** on `parks` (verified: no `parks` references in 013). Only implicit constraints are NOT NULL on `name` and PK uniqueness.

| Check | Result |
|---|---|
| PK distinct (`id`) | 614 / 614 |
| `name NOT NULL` | enforced, 0 violations |
| `acreage` fits `NUMERIC(8,2)` | max=1209.98, fits |

## Geometry

| Check | Result |
|---|---|
| `location` NULL | 0 |
| `location` type | 100% Point |
| `location` in Chicago bbox | 614 / 614 |
| `location` x range | -87.8386 to -87.5288 |
| `location` y range | 41.6479 to 42.0225 |
| `boundary` NULL | 0 |
| `boundary` type | 100% MultiPolygon |
| `boundary` in Chicago bbox (all rings) | 614 / 614 |
| `boundary` polys/park | min=1, median=1, max=60 |

Note: `location` column is missing the GIST index documented in CLAUDE.md (only buildings/cpd/cta_stops are GIST-indexed in migration 001). Not blocking — surfaced for awareness; add only when a nearest-park query lands.

## Area outliers

| Statistic | Value |
|---|---|
| min | 0.01 ac |
| median | 1.96 ac |
| mean | 14.45 ac |
| max | 1209.98 ac (Lincoln) |
| acreage = 0 | 0 |
| acreage < 0.1 ac | 10 |
| acreage < 1 ac | 233 (38%) |
| acreage > 500 ac | 3 (Lincoln 1210, Burnham 658, Jackson 552) |

**Top 10 by acreage:** Lincoln (1210), Burnham (658), Jackson/Andrew (552), Washington/George (350), Marquette (316), Grant (295), Big Marsh (295), Humboldt (211), Calumet (181), Garfield (176). All match known Chicago Park District realities.

**Tiny parks (<0.1 ac):** 10 rows — plausible (pocket parks, plazas, traffic-circle greenspace). No 0-acre or negative entries.

## Type distribution

No `type` / `category` / `class` column exists in `parks`. Source (ArcGIS CW_414) does not provide one in the silver projection. Distribution check N/A.

## Drift

| vs 2026-05-15 | Delta |
|---|---|
| Row count | 0 (614 → 614) |
| Null counts | unchanged (all zero before and after) |

Freshness signal unavailable: `parks` has no `updated_at`, and `pipeline_runs` is empty (0 rows) — no per-source last-run timestamp recorded. Source is documented as static/quarterly; absence of drift is consistent with that cadence.

## Recommendation

**Status: CLEAN — no action required.**

Optional, only when a caller needs it:
- Add `CREATE INDEX parks_location_gix ON parks USING GIST(location)` the first time a nearest-park query is written.
- Backfill `pipeline_runs` for parks (or add `parks.updated_at`) only if the UI starts displaying a "parks last refreshed" timestamp — not before.
