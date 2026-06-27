# displacement_typology — DQ Audit

**Date:** 2026-05-27
**Source:** DePaul IHS / Urban Displacement Project Chicago — per-tract gentrification/displacement typology (vintage 2013–2018)
**Schema:** `supabase/migrations/020_create_displacement_typology.sql`
**Mode:** Read-only

## Summary

Table is clean and stable. 1,982 rows, zero NULLs, zero duplicates, zero CHECK violations, 11 typology categories — all identical to 2026-05-15 audit. Confirmed FK gap: 679 geoids (34.3%) sit outside Chicago in suburban Cook + collar counties (DuPage, Kane, Lake, McHenry, Will). Of the 1,303 matched geoids, 100% are Cook County (FIPS 17031); 45 Chicago tracts in `tracts` have no typology row (vintage-2018 source predates current ACS tract set). Static reference data — recommend leaving as-is.

## Row count

| Metric | Value |
|---|---|
| Current rows | 1,982 |
| Prior audit (2026-05-15) | 1,982 |
| Drift | 0 |

## NULL

| Column | NULLs | % |
|---|---|---|
| geoid | 0 | 0.00% |
| typology | 0 | 0.00% |

## Constraint

| Check | Result |
|---|---|
| PK `geoid` distinct | 1,982 / 1,982 |
| `displacement_typology_geoid_11` CHECK (`^[0-9]{11}$`) | 0 violations |
| `typology NOT NULL` | 0 violations |
| Migration 013 references to `displacement` | none (grep → no matches) |

No typology-value CHECK exists in mig 020 — the 11 categories are enforced only by source-data conformance, not schema.

## Typology distribution

| Typology | Count | % |
|---|---|---|
| At Risk of Becoming Exclusive | 593 | 29.92% |
| Stable Moderate/Mixed Income | 405 | 20.43% |
| Low-Income/Susceptible to Displacement | 329 | 16.60% |
| Stable/Advanced Exclusive | 189 | 9.54% |
| At Risk of Gentrification | 175 | 8.83% |
| Advanced Gentrification | 93 | 4.69% |
| Ongoing Displacement | 83 | 4.19% |
| Early/Ongoing Gentrification | 46 | 2.32% |
| Becoming Exclusive | 38 | 1.92% |
| High Student Population | 26 | 1.31% |
| Unavailable or Unreliable Data | 5 | 0.25% |

11 categories, identical set and counts vs prior audit. Mig 020 header claims "8 categories" — actual source delivers 11 (including the High Student and Unavailable buckets). Doc/comment is stale, data is correct.

## Referential integrity (FK to tracts)

| Metric | Value |
|---|---|
| Distinct geoids in `displacement_typology` | 1,982 |
| Distinct `tracts.id` | 1,348 |
| Matched (geoid ∈ tracts.id) | 1,303 (65.74%) |
| Unmatched | 679 (34.26%) |
| Chicago (Cook 17031) tracts with typology | 1,303 / 1,348 = 96.7% coverage |
| Chicago tracts missing typology | 45 |

**Unmatched 679 by state+county FIPS:**

| FIPS | County | Count |
|---|---|---|
| 17043 | DuPage IL | 216 |
| 17097 | Lake IL | 152 |
| 17197 | Will IL | 152 |
| 17089 | Kane IL | 82 |
| 17111 | McHenry IL | 52 |
| 17031 | Cook IL (suburban, not in Chicago tract set) | 15 |
| 17093 | Kendall IL | 10 |

Confirms prior hypothesis — unmatched rows are the Chicago metro region beyond city limits. UDP publishes for the full CMAP region; `tracts` only loads Chicago tracts. No FK is declared in mig 020 (intentional — would require pre-filtering source).

## Drift

None vs 2026-05-15. Row count, NULL counts, distinct geoid count, typology categories and per-category counts, matched/unmatched FK counts — all bit-identical.

## Recommendation

No action. Static one-shot reference; source last published 2018 with no scheduled refresh. Three minor cleanups for whoever touches it next:

- **Fix mig 020 comment:** says "8 categories", actual is 11. One-line edit.
- **Document the 45 Chicago tracts with no typology row** so the building-view UI shows "no typology data" rather than appearing broken on those addresses.
- **Don't add a typology-value CHECK constraint** — source could publish new categories on a future refresh and locking the set would break the load.
