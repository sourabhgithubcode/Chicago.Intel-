# snow_route_restrictions — DQ Audit

**Date:** 2026-05-27  
**Source:** City of Chicago GIS — snow route restrictions  
**Schema:** `supabase/migrations/024_street_restrictions.sql`  
**Mode:** Read-only

## Summary

Table is stable, matches prior audit (144 rows, all `restriction_type='2 INCH'`, 1 row missing from/to street, IDs 1–165 non-contiguous). Geometry 100% valid MultiLineString within Chicago bbox. No drift. Production-ready for the narrow purpose of marking 2-inch snow-route street segments.

## Row count

| Metric | Value |
|---|---|
| Current rows | 144 |
| Prior audit | 144 |
| Drift | 0 |

## NULL

| Column | NULLs | % |
|---|---|---|
| id | 0 | 0.00% |
| on_street | 0 | 0.00% |
| from_street | 1 | 0.69% |
| to_street | 1 | 0.69% |
| restriction_type | 0 | 0.00% |
| geometry | 0 | 0.00% |

Single missing-endpoint row: `id=153, on_street='WASHINGTON PARK'` — likely a park-loop segment with no cross streets in the source feed.

## Constraint

| Check | Result |
|---|---|
| PK `id` distinct | 144/144 |
| `on_street NOT NULL` (mig 024) | 0 violations |
| `geometry(MultiLineString, 4326)` type modifier | 100% conform |
| Migration 013 CHECK constraints for `snow_*` | none defined (grep `snow` in 013 → no matches) |

## Geometry

| Metric | Value |
|---|---|
| NULL geometry | 0 / 144 |
| Geometry type | MultiLineString × 144 |
| SRID | 4326 |
| Lon bbox | [-87.8367, -87.5245] |
| Lat bbox | [41.6446, 42.0222] |
| Within Chicago bbox | yes |
| GIST index `idx_snow_routes_geometry` | declared in mig 024 |

## Restriction type

| Value | Count |
|---|---|
| `2 INCH` | 144 (100%) |

Uniform — the bronze fetcher only loads the 2-inch snow ban segments. Other restriction types (e.g., overnight) live in `winter_overnight_restrictions`.

## ID coverage

| Metric | Value |
|---|---|
| Min id | 1 |
| Max id | 165 |
| Distinct | 144 |
| Missing ids | 21 |
| First gaps | 45, 106, 107, 108, 109, 110, 111, 112, 115, 116 |
| Last gaps | 118, 119, 120, 121, 122, 123, 125, 128, 133, 138 |
| Unique `on_street` | 125 |

Gaps consistent with prior audit — IDs 106–138 missing block matches IDs surfaced in `winter_overnight_restrictions` (45–138). Source dataset is a single GIS feed split by `restriction_type`; gaps are not data loss.

## Drift

None vs 2026-05-15 audit. Row count, restriction_type distribution, missing-endpoint count, unique street count, and ID range all identical.

## Recommendation

No action. Table is a narrow reference layer (2-inch snow ban segments) and is internally consistent. Downstream use should:

- Join by spatial overlap (GIST index present), not by `id`.
- Treat `WASHINGTON PARK` row as a known one-off; don't filter `from_street IS NOT NULL` blindly.
- If a future need surfaces other restriction types, extend the bronze fetcher rather than relaxing the uniform-type assumption silently.
