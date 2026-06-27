# Silver DQ Audit — `building_permits`

**Audited:** 2026-05-27 (read-only)
**Source:** Chicago Data Portal `ydr8-5enu` (DD §13.21)
**Prior audit:** 2026-05-15 (`docs/silver_layer_audit.md`)

## Summary

Stable since prior audit — zero drift, zero new rows. Schema and content match
the 2026-05-15 snapshot exactly. Pipeline has not refreshed in 12 days.

Key findings:
- 226,114 rows · 0 PK duplicates · 100% within Chicago bbox (no spatial outliers)
- `pin` 100% NULL (expected — not in source)
- `reported_cost` 5.65% NULL · 4,419 zero values · max $1.93B (single row, 1,257× p99)
- `category='other'` = 75.4% — driven entirely by 4 known raw types
  (Express Permit, Easy Permit, Signs, Elevator) that have no bucket
- Migration 013 **defines no CHECK constraints on this table** — the category
  CHECK referenced in DATA_DICTIONARY §15 was never installed (013 lines 66-71
  explain the dead-ALTER removal); validity is enforced only in the transformer

## Row count

| | Value |
|---|---|
| Total | 226,114 |
| Prior audit | 226,114 |
| Δ | 0 |

## NULL %

| Column | NULL | % |
|---|---:|---:|
| `id` | 0 | 0.000% |
| `permit_type` | 0 | 0.000% |
| `category` | 0 | 0.000% |
| `issue_date` | 0 | 0.000% |
| `applied_at` | 23 | 0.010% |
| `pin` | 226,114 | 100.000% |
| `address` | 3 | 0.001% |
| `address_norm` | 3 | 0.001% |
| `reported_cost` | 12,777 | 5.651% |
| `permit_fee` | 0 | 0.000% |
| `location` | 4,106 | 1.816% |

PK distinct: 226,114 / 226,114 (0 duplicates).

## Constraint compliance

Migration 013 installs **no** CHECK constraints on `building_permits` (table
not present in 013 — see lines 66-71 comment). DATA_DICTIONARY §15 lists
`category IN ('new_construction','renovation','demolition','other')` and
`in_chicago_bbox(location)` as intended; both are spec-only today.

Logical-spec checks (computed in this audit):

| Spec check | Pass | Notes |
|---|---:|---|
| `category IN (...)` | 226,114 / 226,114 | no unknown buckets observed |
| `in_chicago_bbox(location)` | 222,008 / 222,008 non-null | 0 violations |
| `reported_cost >= 0` | 213,337 / 213,337 non-null | 0 negatives |
| `issue_date NOT NULL` | 226,114 / 226,114 | passes |

## Geometry

- 4,106 / 226,114 (1.816%) NULL — matches prior audit exactly
- 222,008 non-null, **all inside Chicago bbox**
  (W -87.940 / E -87.524 / S 41.644 / N 42.023)
- SRID 4326 POINT throughout (transformer rejects out-of-bbox coords to NULL,
  so bbox violations cannot reach silver)

## Category distribution

| Category | Rows | % |
|---|---:|---:|
| `other` | 170,408 | 75.36% |
| `renovation` | 42,529 | 18.81% |
| `new_construction` | 8,617 | 3.81% |
| `demolition` | 4,560 | 2.02% |

**Raw `permit_type` values inside `category='other'`** (n=170,408, 6 distinct):

| Count | % of `other` | `permit_type` |
|---:|---:|---|
| 98,555 | 57.83% | `PERMIT – EXPRESS PERMIT PROGRAM` |
| 45,447 | 26.67% | `PERMIT - EASY PERMIT PROCESS` |
| 15,643 | 9.18% | `PERMIT - SIGNS` |
| 7,447 | 4.37% | `PERMIT - ELEVATOR EQUIPMENT` |
| 1,953 | 1.15% | `PERMIT - REINSTATE REVOKED PMT` |
| 1,363 | 0.80% | `PERMIT - SCAFFOLDING` |

100% of "other" is accounted for by 6 known raw types. None contain the
keywords the transformer matches (`NEW CONSTRUCTION` / `RENOVATION` /
`ALTERATION` / `REPAIR` / `REHAB` / `WRECK` / `DEMOLITION`). Express and
Easy permit programs alone are 84.5% of "other" and 63.6% of all permits —
they are administrative wrappers covering many trades and cannot be
single-bucketed from `permit_type` alone.

## Outliers (`reported_cost`)

| Stat | Value |
|---:|---:|
| n (non-null) | 213,337 |
| min | $0 |
| zero values | 4,419 |
| p25 | $2,000 |
| median | $10,000 |
| mean | $266,374 |
| p75 | $37,000 |
| p90 | $200,000 |
| p95 | $500,000 |
| p99 | $3,000,000 |
| max | $1,934,275,000 |

| Threshold | Rows |
|---|---:|
| `> $50M` | 111 |
| `> $100M` | 47 |
| `> $500M` | 11 |
| `> $1B` | 1 |

**Top 5 by `reported_cost`** (all but #2 and #6 are `category='other'`):

| Cost | Category | Type | Address | Issue |
|---:|---|---|---|---|
| $1,934,275,000 | other | EXPRESS PERMIT | 160 W CHICAGO AVE | 2024-08-05 |
| $1,000,000,000 | renovation | RENOVATION/ALTERATION | 700 N CLARK ST | 2020-01-17 |
| $872,523,579 | other | EASY PERMIT | 8842 S BLACKSTONE AVE | 2021-11-16 |
| $846,818,886 | other | EASY PERMIT | 6319 S LAVERGNE AVE | 2022-11-15 |
| $809,418,886 | other | EASY PERMIT | 9631 S WALLACE ST | 2022-05-17 |

The $1.93B Express Permit at 160 W Chicago Ave is implausible for that
permit program (typically minor work) and is almost certainly a data-entry
error in the source. Several of the high-Easy-Permit rows are at residential
South Side addresses — also implausible.

## Date / status

- `issue_date` range: **2020-01-01 → 2026-05-10** (matches DATE_FLOOR in
  `fetch_building_permits.py`)
- `applied_at` range: **2005-12-07 → 2026-05-10** (applications can predate
  issue_date by years; one extreme >18yr lag)
- 23 rows have `applied_at` NULL
- No `status` column exists in silver schema — the source field
  (`current_status` / `status_*`) is not carried forward

**By year (issue_date):**

| Year | Rows |
|---:|---:|
| 2020 | 38,512 |
| 2021 | 39,124 |
| 2022 | 38,336 |
| 2023 | 34,389 |
| 2024 | 33,442 |
| 2025 | 32,044 |
| 2026 | 10,267 |

## Drift since 2026-05-15

| Metric | Value |
|---|---:|
| Rows added | **0** |
| `issue_date >= 2026-05-15` | 0 |
| `applied_at >= 2026-05-15` | 0 |
| Latest `issue_date` | 2026-05-10 |

No refresh has run since the prior audit. Table is frozen at the
2026-05-10 → 2026-05-12 bronze load.

## Recommendation

1. **Install the §15 CHECK constraints**, in the migration that re-creates
   the table (per the 013 comment: "add its constraints in the creating
   migration, not back here"). The two specced constraints —
   `category IN (...)` and `in_chicago_bbox(location)` — both already pass
   100% of current rows, so `NOT VALID` is unnecessary; install as
   immediately-validated.

2. **Expand `_CATEGORY` in `scripts/transformers/building_permits.py`.**
   All 6 raw types in "other" are known and stable. Mechanical mapping:
   - `SIGNS` → `signage`
   - `ELEVATOR EQUIPMENT` → `mechanical`
   - `SCAFFOLDING` → `scaffolding`
   - `REINSTATE REVOKED PMT` → `reinstate`
   - `EXPRESS PERMIT PROGRAM` + `EASY PERMIT PROCESS` → keep as `other` or
     split into `express` / `easy` — these are program wrappers, not work
     types, so the §9.3.2 construction-pipeline factor will continue to
     ignore them.

   Adding 4 buckets drops `other` from 75.4% → 63.6% (Express + Easy
   together). Requires updating the `category IN (...)` CHECK to include
   the new values **before** silver reload, or the CHECK above will reject
   the new rows.

3. **Cap or flag `reported_cost` outliers.** 47 rows over $100M, 11 over
   $500M, top value $1.93B — all on Express/Easy permits or single
   residential addresses. Options:
   - Add a transformer-side sanity cap (e.g. NULL out values > $500M and
     count drops via `validation.assert_failure_rate`)
   - Or surface a `cost_suspect` boolean flag rather than dropping data
   Decision should wait for the §9.3.2 caller — until something reads
   `reported_cost`, no cleanup is needed.

4. **`pin` 100% NULL is expected** (not in source). Reconcile to
   `buildings.pin` via `address_norm` is the spec path (DD §13.21
   "Status" line) — defer until the §9.3.2 factor has a concrete caller,
   per the data-load freeze.

5. **No status column** — if the §9.3.2 factor needs to filter out
   withdrawn/cancelled permits, the transformer must start carrying
   `current_status` from the source. Currently every row is treated as
   issued-and-valid.
