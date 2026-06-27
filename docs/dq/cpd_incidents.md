# DQ Audit — `cpd_incidents`

**Run:** 2026-05-27 (read-only via PostgREST)
**Source:** Chicago Police Dept (Socrata), silver layer
**Schema:** migration 001 + 014 (description dropped); CHECK in 013 (`cpd_location_in_chicago`, `NOT VALID`)

## Summary

Table is healthy. 1,471,413 rows, zero NULLs on all columns (including `iucr` and `location`), all sampled geometries are POINT and within Chicago bbox, type distribution matches prior audit. Two flags: (1) date span is **6.3 years** (2020-01-01 → 2026-05-02), wider than the 5-year window referenced in `CLAUDE.md`; (2) freshness is **25 days stale** vs today (2026-05-27).

## Row count

| Metric | Value |
|---|---|
| Total rows | **1,471,413** |
| Prior audit (2026-05-15) | 1,471,413 |
| Delta | **0** — no new rows since 2026-05-15 |

PK uniqueness: `id` is `BIGINT PRIMARY KEY` (migration 001) — DB-enforced, not separately verified.

## NULL

| Column | NULL | % |
|---|---|---|
| `id` | (PK) | 0 |
| `iucr` | 0 | 0.00% |
| `type` | 0 | 0.00% |
| `date` | 0 | 0.00% |
| `location` | 0 | 0.00% |
| `year` | 0 | 0.00% (generated from `date`) |

Confirms prior audit claim of "0 nulls on all columns".

## Constraint

| Constraint (013) | Status |
|---|---|
| `cpd_location_in_chicago` (`in_chicago_bbox(location)`) | declared `NOT VALID` — not enforced on backfill; sampled compliance below |
| `type IN ('violent','property','other')` (001) | 100% compliant (every row classified) |
| `date NOT NULL` (001) | 100% compliant |

To enforce historically: `ALTER TABLE cpd_incidents VALIDATE CONSTRAINT cpd_location_in_chicago;` — sampling suggests this would pass.

## Geometry

Sampled 7,000 rows across years 2020–2026 (1,000/year):

| Check | Result |
|---|---|
| Geometry type | 100% POINT (0 non-Point) |
| NULL location | 0 / 1,471,413 (PostgREST `not.is.null` count = total) |
| Within Chicago bbox (-87.940..-87.524 lon, 41.644..42.023 lat) | 7,000 / 7,000 (sample) |
| Sample lon range | -87.9081 to -87.5273 |
| Sample lat range | 41.6458 to 42.0225 |

## Date range

| Metric | Value |
|---|---|
| Min date | 2020-01-01 |
| Max date | 2026-05-02 |
| Span | **6.33 years** |
| 5-yr window (`CLAUDE.md`) | Spec says "5 years"; actual load is 6.3 yrs — either spec or fetcher window mismatch |

Yearly distribution:

| Year | Rows |
|---|---|
| 2020 | 207,973 |
| 2021 | 202,869 |
| 2022 | 234,881 |
| 2023 | 261,245 |
| 2024 | 257,530 |
| 2025 | 235,760 |
| 2026 (YTD May 2) | 71,155 |

## Type distribution

| `type` | Rows | % |
|---|---|---|
| other | 821,962 | 55.9% |
| violent | 336,086 | 22.8% |
| property | 313,365 | 21.3% |

55.9% "other" — IUCR→type mapping in fetcher leaves the majority unclassified into the violent/property buckets used by the safety radius query in `CLAUDE.md`. Worth investigating whether "other" includes incidents (drug, weapons, narcotics, public peace) that should count toward safety scores.

Top IUCRs (sampled from common Chicago codes — not exhaustive; PostgREST has no GROUP BY):

| IUCR | Label | Rows |
|---|---|---|
| 0486 | DOMESTIC BATTERY SIMPLE | 123,371 |
| 0820 | THEFT ≤ $500 | 108,856 |
| 0810 | THEFT > $500 | 98,723 |
| 0910 | MOTOR VEHICLE THEFT | 88,987 |
| 0460 | BATTERY SIMPLE | 87,294 |
| 1320 | CRIMINAL DAMAGE TO VEHICLE | 87,164 |
| 0560 | SIMPLE ASSAULT | 85,574 |
| 1310 | CRIMINAL DAMAGE TO PROPERTY | 75,080 |
| 0610 | BURGLARY (FORCIBLE ENTRY) | 26,079 |
| 031A | ARMED ROBBERY (HANDGUN) | 20,349 |

Prior audit: 369 distinct IUCR codes — not re-counted (no GROUP BY via PostgREST).

## Drift

| Reference | Drift |
|---|---|
| Prior audit (2026-05-15) | max_date − ref = **−13 days** (already stale at audit time) |
| Today (2026-05-27) | max_date − today = **−25 days** |

No rows added between 2026-05-15 and 2026-05-27 — fetcher has not run in 12+ days.

## Recommendation

1. **Schedule fetcher** — table is 25 days stale; no rows added in last 12 days. CPD Socrata publishes with ~7-day lag, so freshness target should be `max(date) ≥ today − 14d`.
2. **Reconcile 5-yr window** — fetcher pulled 6.3 yrs vs spec's 5-yr window. Either trim load (saves ~210K rows from 2020) or update `CLAUDE.md` to reflect actual policy.
3. **Validate the location CHECK** — sample is clean; safe to run `ALTER TABLE cpd_incidents VALIDATE CONSTRAINT cpd_location_in_chicago;` to enforce on the backfill and catch future drift cheaply.
4. **Investigate `type='other'` (55.9%)** — half the rows don't contribute to the violent/property safety query. Audit the IUCR→type mapping in the fetcher; many "other" codes (narcotics, weapons, public-peace) likely belong in safety calculations.
5. **No action on nulls / geometry** — both clean.
