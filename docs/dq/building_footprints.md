# DQ Audit: building_footprints
**Generated:** 2026-05-27
**Prior audit:** 2026-05-15
**Rows:** 820,598 (prior: 820,598)

## Summary
Row count matches prior baseline exactly. Table is minimal (2 columns: `bldg_id`, `geometry`) and clean — 0 NULLs on either column, all rows MultiPolygon EPSG:4326 in Chicago bbox. **Schema has no governing migration** (not defined in 001 or 013); table was created out-of-band by `load_building_footprints.py`. One sentinel-looking row `bldg_id = 0` exists with a real 1,761 m² polygon. No FK to `buildings` is possible — `bldg_id` is City GIS ID, `buildings.pin` is Cook County assessor PIN; different keyspaces.

## Row count
- Current: 820,598 (PostgREST estimated count)
- Prior: 820,598
- Delta: 0

## NULL analysis
| Column | NULL % | Note |
|---|---|---|
| bldg_id | 0.0% | PK |
| geometry | 0.0% | all rows have geometry |

Schema is exactly two columns — no `updated_at`, `source_url`, `the_geom_area`, `created_at`, etc.

## Constraint compliance
- **No migration defines this table.** Grep across `supabase/migrations/*.sql` returns zero matches for `footprint` or `building_footprints`. Migration 013 has no CHECK/NOT NULL block for it. The table was created ad-hoc (likely by the first `upsert` in `scripts/load_building_footprints.py`).
- Loader-implied invariants are met by the data: `bldg_id` non-null integer PK ✓, `geometry` non-null ✓.
- Transformer (`scripts/transformers/building_footprints.py`) dedupes by `bldg_id` and filters empty geometries; the table reflects that filtering.

## Geometry / spatial
| Check | Result | Notes |
|---|---|---|
| NULL geometry | 0 / 820,598 | — |
| Type = MultiPolygon | 200/200 sampled | matches loader's `MultiPolygon`-only path |
| CRS | EPSG:4326 on all sampled | embedded in GeoJSON `crs` |
| Vertices outside Chicago bbox (lon −87.95 to −87.50, lat 41.63 to 42.05) | 0 / 1,397 sampled vertices | — |
| Centroids outside Chicago bbox | 0 / 1,000 sampled rows | — |

## Outliers (footprint area, sample n=1,000 of first-PK ordered rows)
Areas computed client-side from GeoJSON (deg² → m² via lat-adjusted scale; ±~1% accuracy at Chicago latitude).

| Metric | Value |
|---|---|
| min | 2.7 m² |
| p05 | 33.4 m² |
| median | 120.7 m² |
| p95 | 864.9 m² |
| p99 | 1,426.2 m² |
| max | 3,774.1 m² |
| Tiny (<1 m²) | 0 |
| Small (<10 m²) | 16 (1.6%) |
| Giant (>50,000 m²) | 0 |

Bottom of the distribution (2.7–4.4 m² polygons, ~30–50 sq ft) are plausibly sheds, transformer boxes, or fragmented digitizations. No pathological zero-area or world-spanning polygons in sample. **Caveat:** sample is biased to low `bldg_id` (PostgREST capped at 1,000 rows/request, no SQL RPC available to scan all 820K); rerun via a server-side aggregate when an `exec_sql` RPC is added.

## Referential integrity
- **No FK to `buildings.pin`** — and none is possible. `bldg_id` is City of Chicago GIS building ID (source dataset `syp8-uezg`); `buildings.pin` is Cook County 14-digit assessor PIN. Different upstream systems, no public crosswalk in this repo.
- The intended join path for "footprint of this building" is spatial (PostGIS `ST_Within` / `ST_Intersects` between `buildings.location` point and `building_footprints.geometry`), not a key join. No orphan check applies.

## PK distinctness
- min `bldg_id` = 0, max = 894,615 → ID space spans ~895K for 820,598 distinct rows (gaps consistent with city's filtering / deduping at source).
- `bldg_id = 0` exists as one row with a valid 1,761 m² polygon at (-87.866, 41.974). Worth confirming with the source dataset whether `0` is a real ID or a sentinel for "ID unknown" — if sentinel, drop on next reload.
- PK distinctness inferred from loader behavior (transformer's `seen: set[int]` and PostgREST upsert merge) plus 0 NULLs; cannot run a server-side `COUNT(DISTINCT)` without an SQL RPC, but no contradicting evidence found.

## Freshness
- **No `updated_at` / `loaded_at` column.** No way to query freshness from the table itself.
- Last load is recorded only in `pipeline_runs` (see migration 005) — not in this table.

## Drift from 2026-05-15
| Check | Direction |
|---|---|
| Row count 820,598 | unchanged |
| NULL counts (both columns) 0 | unchanged |
| Prior audit's "8 dropped / 820,606" note (footprint dedupe loss) | consistent — current 820,598 = 820,606 − 8 |
| Schema | unchanged (still bldg_id + geometry only) |

## Recommendation
- **Add a migration for this table** (e.g. `025_create_building_footprints.sql`) — make the schema declarative: `bldg_id BIGINT PRIMARY KEY`, `geometry GEOMETRY(MULTIPOLYGON, 4326) NOT NULL`, GIST index. Right now the table only exists because someone ran `load_building_footprints.py`; a fresh Supabase rebuild would skip it.
- **Decide on `bldg_id = 0`.** Source-check whether the City emits `0` as a real ID or as a null sentinel. If sentinel, filter in the transformer (`if bldg_id == 0: continue`) and reload.
- **Skip adding `updated_at`** unless a caller needs it (per the no-bloat rule). Freshness lives in `pipeline_runs`.
- **Don't attempt a `bldg_id → pin` FK.** The mapping is spatial-only.
- **Defer full-table area outlier scan** until an `exec_sql` RPC (or direct PG connection) is wired up — sampling the first 1,000 PK-ordered rows is not representative of the long tail.
