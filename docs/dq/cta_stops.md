# cta_stops — Data Quality Audit

**Generated:** 2026-05-27  
**Source:** CTA GTFS `stops.txt` (transitchicago.com)  
**Prior audit:** 2026-05-15 (`docs/silver_layer_audit.md` §cta_stops)  
**Read-only.** No code or data modified.

## Summary

Table is structurally clean. Zero drift vs. prior audit (row count, nulls, accessibility unchanged). One known gap reaffirmed: `lines` is an empty array on 100% of rows — transformer intentionally leaves it empty for V1 (per `scripts/transformers/cta.py` line 14). Migration 013 adds no CHECKs for this table.

## Row count

| Metric | Value | vs. Prior |
|---|---|---|
| Total rows | 10,833 | unchanged |

## NULL

| Column | NULL count | NULL % |
|---|---|---|
| id | 0 | 0.00% |
| name | 0 | 0.00% |
| lines | 0 | 0.00% (but all `[]`) |
| accessible | 0 | 0.00% |
| location | 0 | 0.00% |

## Constraint

- **PK distinct:** 10,833 distinct `id` / 10,833 rows — clean.
- **id range:** 1 – 60,013 (sparse — matches CTA GTFS stop_id space).
- **Migration 013 CHECK constraints:** **none defined for `cta_stops`.** Bbox / NOT-NULL constraints exist on `buildings`, `cpd_incidents`, `complaints_311`, `tracts` only. (013 has no `cta` reference.)
- **Schema-level (migration 001):** `id PK`, `name NOT NULL`, `accessible DEFAULT FALSE`, `location GEOMETRY(POINT, 4326)`. All satisfied.

## Geometry

| Check | Result |
|---|---|
| Type | 100% `Point` (0 non-point) |
| SRID | 4326 (declared in schema) |
| Lat range | 41.64417 – 42.02296 |
| Lng range | −87.90422 – −87.52571 |
| Inside Chicago bbox (lat 41.644–42.023, lng −87.940 – −87.524) | 10,833 (100.00%) |
| Outside Chicago bbox | 0 |

Transformer (`scripts/transformers/cta.py`) hard-filters non-Chicago lat/lng, so suburban stops (Oak Park, Evanston) are dropped at load — no "slight margin for suburbs" rows exist by design.

## Accessibility

| accessible | Count | % |
|---|---|---|
| true | 10,734 | 99.086% |
| false | 99 | 0.914% |
| null | 0 | 0.000% |

Matches prior 99.1% exactly. Note: ~99% is suspiciously high vs. CTA's published station-level accessibility (~70%). Likely because `wheelchair_boarding=1` in GTFS is set on most bus stops by default; station platform inheritance may inflate the count. Transformer reads `wheelchair_boarding == 1` directly — no upstream validation.

## Routes

**Critical gap (known):** `lines` column is `[]` on **10,833 / 10,833 rows (100%)**.

- 0 stops have any line assigned.
- 0 multi-line stops.
- Routes histogram empty.

Transformer comment (line 13–14): *"`lines` requires joining stop_times → trips → routes; left empty for V1. Backfill is a follow-up."*

**Downstream impact:** any UI/query that filters by transit line (e.g., "nearest Red Line stop") cannot work today. `name` often contains line text (e.g., "95th Red Line Station") but is unstructured.

**Name duplication:** 6,104 distinct names / 10,833 rows. Up to 11 platforms share a name (e.g., "Jefferson Park Transit Center"). Expected — GTFS `stop_id` is per-platform, not per-station. Prior audit notes this.

## Drift

Zero drift vs. 2026-05-15 audit:

| Metric | Prior | Current |
|---|---|---|
| Rows | 10,833 | 10,833 |
| Nulls (all cols) | 0 | 0 |
| Accessible | 99.1% | 99.086% |
| Lat range | 41.644 – 42.023 | 41.64417 – 42.02296 |

No freshness column on the table (no `loaded_at` / `updated_at`) — drift detected purely by structural comparison. CTA GTFS is refreshed quarterly per `CLAUDE.md`; no evidence of re-load since 2026-05-12 bronze window.

## Recommendation

**P1 — Backfill `lines`.** This is the blocker. Add the GTFS join (`stop_times` → `trips` → `routes`) in `fetch_cta.py` and re-upsert. Without it, no transit-line filtering works downstream. Affects `nearest CTA stop` query pattern in `CLAUDE.md` (which currently selects `lines` knowing it's empty).

**P3 — Audit accessibility source.** Verify whether GTFS `wheelchair_boarding=1` for bus stops is meaningful or a default. If default, the 99.1% number is misleading and should not be surfaced as a confidence-rated metric.

**P4 — Add CHECK constraints in next migration.** Migration 013 skipped this table. Minimum: `in_chicago_bbox(location)` (transformer already enforces — constraint just makes it explicit) and `name IS NOT NULL` (already enforced by 001, but no CHECK form). Low priority — transformer is the gate today.

**P4 — Add a `loaded_at` column** if a future change wants freshness tracking. Skip until a caller needs it (per CLAUDE.md "no bloat" rule).

No P0 issues. Table is safe for use as-is for location-only queries.
