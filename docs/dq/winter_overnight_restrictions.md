# DQ Audit — `winter_overnight_restrictions`

**Date:** 2026-05-27
**Source migration:** `024_street_restrictions.sql`
**Prior audit:** `docs/silver_layer_audit.md` (2026-05-15, 20 rows)

## Summary

Clean. 20 rows, 0 nulls, all geometry valid `MultiLineString` 4326 inside Chicago bbox, all `restriction_type='OVERNIGHT'`. Identical to prior audit — no drift. Schema has no CHECK constraints; all integrity passes trivially. One minor cosmetic note: 4 `on_street` values lack a directional prefix (`N/S/E/W`), inconsistent with the other 16.

## Row count

| Metric | Value |
|---|---|
| Total rows | 20 |
| Prior audit | 20 |
| Delta | 0 |

## NULL

| Column | Nulls | % |
|---|---|---|
| id | 0 | 0% |
| on_street | 0 | 0% |
| from_street | 0 | 0% |
| to_street | 0 | 0% |
| restriction_type | 0 | 0% |
| geometry | 0 | 0% |

## Constraint

| Check | Result |
|---|---|
| PK (`id`) distinct | 20/20 |
| `on_street` NOT NULL | pass |
| `geometry` type = MultiLineString, SRID 4326 | pass (all 20) |
| CHECK constraints in migration 013 | none defined for this table |

## Geometry

| Check | Result |
|---|---|
| Null geometry | 0 |
| Geometry type | MultiLineString (all 20) |
| Single-LineString MultiLineStrings | 13/20 (could be plain LineString; tolerable) |
| Global bbox lng | [-87.80153, -87.52453] |
| Global bbox lat | [41.70268, 42.01940] |
| Out of Chicago bbox | 0 |

## Restriction type

| Value | Count |
|---|---|
| OVERNIGHT | 20 |

Uniform. Column adds no information for this table — only useful if combined with `snow_route_restrictions` in a union view.

## Drift

No drift since 2026-05-15. Same 20 rows, same id set (45, 106–123 with gaps, 125, 133, 138), same 19 unique `on_street` values, same uniform `restriction_type`. Source is a static city GIS extract — not expected to change between bulk refreshes.

## Other observations

- 4 `on_street` rows missing directional prefix: `103RD ST`, `79TH ST`, `ARCHER AVE`, `CENTRAL AVE`. Other 16 use `N/S/E/W` prefix. Cosmetic — does not affect joins (this table is not joined to `streets` today).
- IDs are sparse subset of `snow_route_restrictions` id space (45–138), confirming both tables come from the same upstream restriction dataset filtered by type.

## Recommendation

No action. Table is healthy and stable. Defer the directional-prefix normalization until a fetcher or reconcile script needs to join this table to `streets` — current code does not. Per "no bloat" rule, do not add CHECK constraints or normalization passes until a real caller exists.
