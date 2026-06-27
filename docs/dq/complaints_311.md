# DQ Audit: complaints_311
**Generated:** 2026-05-27
**Prior audit:** 2026-05-15
**Rows:** 454,227 (prior: 454,227)

## Summary
Zero drift since 2026-05-15 — same row count, same max date (2026-05-09), same 2-type distribution. `address_norm` still 100% NULL (P4 in prior audit unresolved). Only 2 of ~10 needed `sr_type` values are fetched (Rodent + Building Violation) — heat / bed-bug still missing, blocks `buildings.heat_complaints` / `buildings.bug_reports` enrichment.

## Row count
- Current: 454,227
- Prior: 454,227
- Delta: 0 — no new bronze→silver load since prior audit

## NULL analysis
Silver schema is `id, type, address, date, location, address_norm` (migration 001 + 005). Task references `sr_number` / `sr_type` — those are bronze names; silver renames to `id` / `type`.

| Column | NULL count | NULL % | Note |
|---|---|---|---|
| id | 0 | 0.00% | PK |
| type | 0 | 0.00% | — |
| address | 22 | 0.00% | bronze `street_address` occasionally blank |
| date | 0 | 0.00% | transformer skips rows with missing `created_date` |
| location | 0 (per-year probes 2020 & 2026 both 100% non-null) | 0.00% | transformer skips rows without lat/lng |
| address_norm | 454,227 | **100.00%** | transformer never computes it (P4 in prior audit, still open) |

Per-year non-null probes (full-table `is.null` query times out — Supabase has no GIST index for IS NULL on `location`):
- 2020: 72,355 non-null location / 72,355 total → 100%
- 2026: 16,373 non-null location / 16,373 total → 100%
- 2020 + 2026 non-null `address_norm`: 0 each → 100% NULL

## Constraint compliance (migration 013)
| Constraint | Status |
|---|---|
| `complaints_311_date_present` (date IS NOT NULL) | ✓ 0 NULL dates |
| `complaints_311_location_in_chicago` (in_chicago_bbox) | ✓ 500 oldest + 500 newest sampled, all inside bbox |
| PK distinct on `id` | ✓ enforced by `BIGINT PRIMARY KEY`; transformer also de-dups via `seen` set |

Both 013 CHECKs are `NOT VALID` — they police new inserts but were never `VALIDATE`d against existing rows. Sampling shows no violations to validate against.

## Geometry / spatial
| Check | Result |
|---|---|
| Geometry type | POINT, SRID 4326 (transformer emits `SRID=4326;POINT(lng lat)`) |
| NULL location | 0 (per-year probes; transformer drops null-coord rows at bronze→silver) |
| Bbox sample (500 oldest IDs) | lat [41.6607, 42.0192], lng [−87.8461, −87.5353] ✓ |
| Bbox sample (500 newest IDs) | lat [41.6545, 42.0197], lng [−87.8436, −87.5273] ✓ |
| Chicago bbox reference | lat [41.644, 42.023], lng [−87.940, −87.524] |

## Type distribution
| Type | Count | % |
|---|---|---|
| Rodent Baiting/Rat Complaint | 318,358 | 70.09% |
| Building Violation | 135,869 | 29.91% |
| (any other type) | 0 | 0.00% (verified via `neq` on both known types) |

Only 2 distinct values present — matches `fetch_311.py` Socrata filter. **Missing:** `Heat`, `Bed Bug`, `Sanitation Code Violation`, etc.

## Date / status
**Date range:** 2020-01-01 → 2026-05-09 (max date = prior audit's max date)

**Per-year totals:**
| Year | Count |
|---|---|
| 2020 | 72,355 |
| 2021 | 87,181 |
| 2022 | 71,651 |
| 2023 | 76,329 |
| 2024 | 66,303 |
| 2025 | 64,035 |
| 2026 (YTD 2026-05-09) | 16,373 |

**Freshness:** newest date 2026-05-09 → 18 days stale as of 2026-05-27 generation date. Same staleness as prior audit (no refresh since 2026-05-15).

**Status:** silver has no `status` column (bronze `status` not promoted). Not auditable.

## Drift from 2026-05-15
| Metric | Prior | Current | Delta |
|---|---|---|---|
| Row count | 454,227 | 454,227 | 0 |
| Max date | 2026-05-09 | 2026-05-09 | 0 days |
| Distinct types | 2 | 2 | 0 |
| Rodent count | 318,358 | 318,358 | 0 |
| Building Violation count | 135,869 | 135,869 | 0 |
| `address_norm` NULL % | 100% | 100% | unchanged |

**No bronze→silver load has run for this source since 2026-05-12 bronze ingest.** Data-load freeze (per `project_data_load_freeze.md`) is holding.

## Recommendation
1. **Backfill `address_norm`** (P4 from prior audit) — one-pass UPDATE using the same normalizer used by `buildings.address_norm`. Migration 005's index on `address_norm` is currently useless. Required for any 311↔buildings spatial-then-textual join.
2. **Expand `fetch_311.py` filter** (P3) to also pull `Heat`, `Bed Bug`, and `Sanitation Code Violation` Socrata types. Without these, `buildings.heat_complaints` and `buildings.bug_reports` stay at 0 forever (root cause of buildings P2).
3. **Schedule a refresh** — data is 18 days stale; running fetch should add ~3 weeks of 311 records.
4. **No action needed** on row count, geometry, bbox, PK uniqueness, or date integrity — all clean and stable.
5. Address the silver schema doc-vs-code gap: prior audit and this task both reference `sr_number`/`sr_type`/`address_norm`; actual silver columns are `id`/`type`/`address`/`address_norm`. Update DATA_DICTIONARY if it lists bronze names for this silver table.
