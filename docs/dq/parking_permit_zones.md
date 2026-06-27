# DQ Audit — `parking_permit_zones`

**Date:** 2026-05-27 · **Source:** Chicago Data Portal `u9xt-hiju` · **Geometry:** N/A — text-only table.

## Summary

10,372 rows, PK unique, zero NULLs on core fields. Status mix (95.22% ACTIVE) and side balance (E=5,185 / O=5,187) match expectations for a citywide residential permit dataset. **163 rows have invalid ward** (142 with `ward=0` + 21 with `ward=NULL`) — prior audit reported only 21 because it conflated NULL with the zero anomaly. No CHECK constraints exist in the migrations for this table (table created post-013, not in any tracked migration). Drift vs 2026-05-15: row count unchanged.

## Row count

- Live: **10,372**
- Prior (2026-05-15): 10,372
- Delta: **0**

## NULL %

| Column            | Nulls | %      |
|-------------------|------:|-------:|
| id                | 0     | 0.00%  |
| zone              | 0     | 0.00%  |
| street_name       | 0     | 0.00%  |
| street_direction  | 0     | 0.00%  |
| street_type       | 63    | 0.61%  |
| address_low       | 0     | 0.00%  |
| address_high      | 0     | 0.00%  |
| odd_even          | 0     | 0.00%  |
| ward              | 21    | 0.20%  |
| status            | 0     | 0.00%  |

## Constraint compliance

- **No CHECK constraints declared for `parking_permit_zones` in any migration** (grep across `supabase/migrations/*.sql` returns zero matches). Migration 013 tightened other silver tables but not this one — table appears to have been created outside the tracked migration set (consistent with DATA_DICTIONARY §2419 calling it "Bronze-only as of 2026-05-11; silver lands when freeze lifts").
- PK uniqueness: **10,372 distinct ids / 10,372 rows** — clean.
- Implicit ward range expectation (1–50): **violated by 163 rows** (see below).

## Ward distribution

| Bucket         | Count  | Note                              |
|----------------|-------:|-----------------------------------|
| ward = 0       | **142** | Invalid sentinel — prior=21 (mis-reported) |
| ward NULL      | 21     | Same as prior                     |
| ward 1–50      | 10,209 | Min=1, Max=50                     |
| ward < 1 (non-null) | 142 | All are the `ward=0` rows         |
| ward > 50      | 0      |                                   |

**Top 5 wards:** 43 (609), 44 (488), 1 (405), 2 (385), 25 (361). All within the North Side / Loop residential-permit core — plausible.

**Note on prior audit drift:** prior `silver_layer_audit.md` line 234 says "21 null/zero wards (invalid)". Actual is **21 null + 142 zero = 163**. The `ward=0` rows cluster in zone 1676 (Near South Side) and zone 2438 (Far South Side) — looks like a source-side ward-assignment gap, not a transformer bug (`ward_low`/`ward_high` both come through as 0 from the City portal).

## Status

| Status     | Count  | %      |
|------------|-------:|-------:|
| ACTIVE     | 9,876  | 95.22% |
| RESCINDED  | 496    | 4.78%  |
| NULL       | 0      | —      |

Only two distinct values. Matches prior (9,876 ACTIVE).

## Zones / streets

- **Distinct zones:** 2,048 (matches prior)
- **Distinct street_name only:** 771 (matches prior)
- **Distinct (direction, street_name) pairs:** 956

## Address checks

- `address_low > address_high`: **0 rows** — clean.
- `address_low == 0` or `address_high == 0`: **13 rows** — minor; likely intersection-anchored segments.
- Negative addresses: **0 rows**.
- `odd_even` distribution: E=5,185 / O=5,187 / no `B` (both) / no NULL — matches prior.

## Drift from 2026-05-15

| Metric              | Prior  | Now    | Δ    |
|---------------------|-------:|-------:|-----:|
| Total rows          | 10,372 | 10,372 | 0    |
| ACTIVE              | 9,876  | 9,876  | 0    |
| Distinct zones      | 2,048  | 2,048  | 0    |
| Distinct streets    | 771    | 771    | 0    |
| odd_even E          | 5,185  | 5,185  | 0    |
| odd_even O          | 5,187  | 5,187  | 0    |
| ward NULL           | (lumped) | 21   | —    |
| ward = 0            | (lumped) | 142  | —    |

No drift — table is static between audits (expected: quarterly refresh; last bronze write 2026-05-12 per DATA_DICTIONARY).

## Recommendation

1. **Fix prior-audit miscount.** Update `docs/silver_layer_audit.md` line 234 to "21 null + 142 zero wards = 163 invalid (1.57%)". The "21" figure understates the ward-quality problem by 7×.
2. **No CHECK constraints exist** — when the silver table is formalized in a migration (post-freeze), add: `CHECK (ward BETWEEN 1 AND 50)`, `CHECK (address_low <= address_high)`, `CHECK (odd_even IN ('E','O','B'))`, `CHECK (status IN ('ACTIVE','RESCINDED'))`. Defer the ward constraint until the 163 invalid rows are either dropped or carry a documented exception, otherwise the constraint will reject the next reload.
3. **Investigate ward=0 cluster** — 142 rows concentrate in zones 1676 (Near South) and 2438 (Far South). Either backfill from PIN-via-ward lookup or treat `ward=0` as a sentinel and surface as "ward unknown" in the UI.
4. **No timestamp column** on the silver table — drift detection currently relies on row-count diff only. If quarterly refresh cadence matters, add `loaded_at TIMESTAMPTZ DEFAULT NOW()` when the migration lands.
