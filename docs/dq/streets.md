# DQ Audit: streets
**Generated:** 2026-05-27
**Prior audit:** 2026-05-15
**Rows:** 55,872 (prior: 55,872 — no change)

## Summary

| Severity | Finding |
|---|---|
| RED | `cca_id`, `tract_id` still 100% NULL — `assign_streets_to_polygons()` never ran. Gold `gold_street_summary` cannot key on either. Unchanged from 05-15. |
| RED | `geometry` column type is `LineString` in every row, but migration 007 (re-asserted by 022) declares `GEOMETRY(MULTILINESTRING, 4326)`. Either migration 022 was never applied, or the live column type is still `LINESTRING` and the migration sits unrun. Schema-vs-reality drift. |
| ORANGE | 95 rows with `from_addr = 0 AND to_addr = 0` (alleys / airport ramps / unnumbered segments). Unchanged from 05-15. |
| ORANGE | 2 inverted rows (`from_addr > to_addr`) — both `N Rwy22R Ord` (O'Hare runway centerlines, ids 166866, 166867). Unchanged. |
| GREEN | id PK clean (55,872 distinct), no FK orphans (cca_id/tract_id all NULL → vacuously clean), all geometries non-NULL and inside Chicago bbox, direction prefix present on 100% of rows. |
| INFO | Migration 013 declares **zero** CHECK constraints on `streets` — nothing to validate. |

## Row count
- Total: **55,872** (identical to 2026-05-15)
- Distinct `id`: **55,872** — no duplicates, PK clean

## NULL analysis (all 8 columns)

| Column | NULLs | % | Notes |
|---|---:|---:|---|
| id | 0 | 0.0% | PK |
| name | 0 | 0.0% | |
| name_norm | 0 | 0.0% | |
| from_addr | 0 | 0.0% | 95 rows are 0 (see Address range) |
| to_addr | 0 | 0.0% | 95 rows are 0 |
| cca_id | **55,872** | **100.0%** | reconcile never ran |
| tract_id | **55,872** | **100.0%** | reconcile never ran |
| geometry | 0 | 0.0% | |

No `updated_at` column on this table — drift cannot be measured by timestamp, only by row count.

## Constraint compliance

Migration 013 (`013_data_integrity_constraints.sql`) defines **no** constraints for `streets` (grep on `streets` in 013 returns empty). The only constraints on this table come from 007:

| Constraint (from 007) | Type | Status |
|---|---|---|
| `streets_pkey` (id) | PK | clean — 55,872 distinct |
| `cca_id REFERENCES ccas(id)` | FK | vacuously clean (all NULL) |
| `tract_id REFERENCES tracts(id)` | FK | vacuously clean (all NULL) |
| `name NOT NULL` | NOT NULL | 0 violations |
| `geometry GEOMETRY(MULTILINESTRING, 4326)` | Type | **mismatch — see Geometry** |

## Geometry / spatial

| Check | Result |
|---|---|
| NULL geometry | 0 / 55,872 |
| Geometry type returned by PostgREST | `LineString` on **100%** of rows (55,872) |
| `MultiLineString` rows | **0** |
| Vertex bbox (lon, lat) | [-87.93994, -87.52453] x [41.64459, 42.02293] |
| Chicago reference bbox | [-87.940, -87.524] x [41.644, 42.023] |
| Vertices outside Chicago bbox | 0 lon / 0 lat (of 391,114 vertices sampled) |

**Schema drift.** Migration 007 declares `GEOMETRY(MULTILINESTRING, 4326)` and migration 022 re-asserts it with a `USING geometry::GEOMETRY(MULTILINESTRING, 4326)` cast. Every live row, however, is a single `LineString`. The Socrata source (`6imu-meau`) emits `MultiLineString` GeoJSON, so a LineString-only payload implies either (a) migration 022 never ran and the live column is still `LINESTRING`, or (b) the loader is unwrapping MultiLineString → LineString before insert (which would only work if the column is still `LINESTRING` — `GEOMETRY(MULTILINESTRING)` would reject `LineString` writes). Most likely: **022 is unapplied**.

This needs verification by reading the live column type (`SELECT type FROM geometry_columns WHERE f_table_name='streets'`) — PostgREST cannot expose this. The remediation differs:

- If column type is still `LINESTRING`: re-run migration 022, but on populated data the `USING` cast `LineString → MultiLineString` works trivially via `ST_Multi()`. Safer rewrite: `USING ST_Multi(geometry)::GEOMETRY(MULTILINESTRING, 4326)`.
- If column type is already `MULTILINESTRING`: the loader is silently coercing to LineString, which means the spatial-join function `assign_streets_to_polygons()` will still work (PostGIS treats both the same for `ST_PointOnSurface`), but the schema contract is broken and downstream consumers can't rely on the declared type.

## Address range checks

| Check | Count | Prior | Notes |
|---|---:|---:|---|
| `from_addr = 0 AND to_addr = 0` | **95** | 95 | Alleys, airport ramps, unnamed segments. Unchanged. |
| `from_addr > to_addr` (inverted) | **2** | 2 | Both `N Rwy22R Ord` (O'Hare runway 22R, ids `166866`, `166867`). Unchanged. |
| `from_addr` NULL | 0 | — | |
| `to_addr` NULL | 0 | — | |

Sample zero-range rows: `W 29Th St`, `S Champlain Ave`, `S Wells St`, `S Midway Airport`, `W Westgate Ter`, `W Eisenhower Ib Kennedy Ob Er`, `S Midway Airport Lower Cicero Ave Xr`, `E Mcfetridge Dr N`, `W 87Th St`. These are predominantly highway interchange ramps, airport access roads, and short unsigned segments — expected source noise, not a transformer bug.

## Direction / type distribution

**Direction prefix** (first token of `name`):

| Dir | Count | % |
|---|---:|---:|
| W | 21,245 | 38.0% |
| S | 17,394 | 31.1% |
| N | 12,427 | 22.2% |
| E | 4,806 | 8.6% |
| (none) | 0 | 0.0% |

Every row carries a direction prefix. The W/S skew matches Chicago's grid geometry (the city extends much farther W and S of State/Madison than N or E).

**Top 10 street types** (token before optional trailing direction):

| Type | Count |
|---|---:|
| AVE | 25,902 |
| ST | 19,985 |
| PL | 1,874 |
| RD | 1,236 |
| BLVD | 1,197 |
| DR | 1,109 |
| OB (outbound ramp) | 761 |
| IB (inbound ramp) | 752 |
| ER (entrance ramp) | 618 |
| XR (cross ramp) | 482 |

Long tail includes `RIVER`, `ORD`, `PKWY`, `SB`, `CT`. Highway-ramp types (`OB`, `IB`, `ER`, `XR`, `SB`, `ORD`) account for ~3,400 rows — these are the same population as the airport/expressway segments that show up in the zero-range and inverted-range bands.

## Referential integrity

| FK | Orphan count | Notes |
|---|---:|---|
| `cca_id → ccas.id` | 0 | All NULL — vacuously clean. No CCA mappings exist yet. |
| `tract_id → tracts.id` | 0 | All NULL — vacuously clean. |

Non-null `cca_id` = **0**, non-null `tract_id` = **0**. The reconcile function `assign_streets_to_polygons()` (defined in 007) has not been called against this table. Note: even if it had run, `ccas.geometry` is itself 100% NULL per the 05-15 audit, so the CCA half of the assignment would silently produce zero updates anyway.

## Drift from 2026-05-15

| Metric | 2026-05-15 | 2026-05-27 | Delta |
|---|---|---|---|
| Row count | 55,872 | 55,872 | 0 |
| `cca_id` NULL | 55,872 (100%) | 55,872 (100%) | no change |
| `tract_id` NULL | 55,872 (100%) | 55,872 (100%) | no change |
| Zero-range rows | 95 | 95 | no change |
| Inverted-range rows | 2 | 2 | no change |
| Geometry NULL | 0 | 0 | no change |
| Geometry column-type drift | not flagged | **100% LineString vs declared MultiLineString** | **new finding** |

No table has no `updated_at`/timestamp column, so source-freshness drift can't be checked from row data. Bronze load window (per 05-15) was 2026-05-10..05-12; no evidence of any subsequent refresh.

## Recommendation

Ordered by blast radius into Gold MVs / spatial joins:

1. **Verify and fix the geometry-type drift.** Query `geometry_columns` directly (or read it via `psql` / Supabase SQL editor — not exposed over PostgREST) for `f_table_name='streets'`. If still `LINESTRING`, rewrite 022 to use `USING ST_Multi(geometry)::GEOMETRY(MULTILINESTRING, 4326)` and apply. If already `MULTILINESTRING`, fix the loader to insert MultiLineString WKT (don't unwrap single-element MultiLineStrings before write). Either way, end-state should be 100% `MultiLineString` rows.
2. **Run `assign_streets_to_polygons()`.** Blocked by `ccas.geometry` being 100% NULL — load CCA geometries first (per 05-15 P1), then run this reconcile. Until both run, `gold_street_summary.cca_id` / `tract_id` will be NULL on all 55,872 rows and the §9.7 Street panel cannot key on CCA.
3. **Decide on the 95 zero-range rows.** Add a CHECK like `from_addr >= 0 AND to_addr >= 0 AND (from_addr + to_addr) > 0` only if the product wants to drop them; otherwise document as "unnumbered segments expected from source 6imu-meau" and leave alone. Current behaviour silently keeps them.
4. **Decide on the 2 inverted runway rows.** Either swap `from_addr`/`to_addr` in the transformer for O'Hare runway IDs (cosmetic — they have no address grid meaning), or add a CHECK to reject them. They will not cause real downstream harm because no building joins to a runway centerline.
5. **Consider an `updated_at` column** on `streets` (one column, sourced from the loader timestamp). Without it, drift detection between audits is restricted to row-count comparison, which masks any partial re-loads. Defer until a migration that genuinely needs it; do not add speculatively.
