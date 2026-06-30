# Affordability Engine — Spec (DRAFT for approval)

Status: **DRAFT — awaiting sign-off on weights + transport-cost parameters.**
Owner: Sourabh. Drafted 2026-06-29.

## 1. Goal

A per-neighborhood (CCA) **affordability engine** computed from real, collected
data, surfaced on the citywide map: every neighborhood gets a **1–10** score,
the map recolors by any chosen metric ("color by"), and every component score is
**clickable** to show its value, source, confidence, and weight.

Modeled on the HUD/DOT **Location Affordability Index (LAI v3)** *structure*
(housing + transportation cost as a share of income) — but **recomputed on
current 2019–23 ACS**, not ingested from HUD. Therefore it is **our estimate,
labeled as such**, never presented as HUD's published LAI value.

Philosophy unchanged: show what data says, show the source, show confidence,
show every weight. **Never a recommendation** — a ranked comparison the user
interprets.

## 2. Headline: Modeled H+T Affordability (our estimate)

```
Housing (mo)    = ACS median gross rent            (B25064)            [in repo]
Transport (mo)  = transit_share × transit_pass_cost                    [transit_share: ACS B08301]
                + autos_per_hh × per_auto_cost / 12                    [autos: ACS B25044]
H+T ratio       = (Housing + Transport) × 12 ÷ median_household_income (B19013)
Affordability   = map H+T ratio → 1–10 against HUD's 45% H+T benchmark
                  (≤30% ⇒ ~10; ≥60% ⇒ ~1; linear between — exact curve TBD)
```

- `transit_pass_cost` and `per_auto_cost` are **visible parameters sourced at
  build time** (current CTA pass rate; AAA/IRS per-auto annual cost). NOT
  recalled from memory.
- **Honesty label (required):** "Modeled H+T affordability — our estimate using
  2019–23 ACS + current transit/auto cost parameters. Not HUD's published LAI.
  Confidence 6/10." Transportation cost is a simplified model, **not** HUD's SEM.

## 3. Community Vulnerability sub-score (long-term affordability pressure)

1–10 from ACS, higher = more affordable/stable (vulnerability inverted):
- % families below poverty       (B17001)            — not yet fetched
- Housing vacancy rate           (B25002)            — fetched, not stored
- Renter share of occupied units (B25003)            — fetched, not stored
- Median income vs Area Median Income (B19013 + area)— income fetched, not stored

Each normalized across the 77, averaged. "Over time"/trend deferred (needs ≥2
ACS vintages; current pipeline is single-vintage).

## 4. Lifestyle sub-scores (OSM/Overpass — reuse existing amenity client)

- **Vibe** — density of food/coffee/nightlife/entertainment POIs per CCA → 1–10.
- **Bikeability** — cycleway / bike-lane length density per CCA → 1–10. (new)
- **Runnability** — park area + path/trail length per CCA → 1–10. (parks table + OSM)

All three currently empty: `vibe_score`/`run_score` columns NULL; bikeability has
no column. Sourced from OSM to match the amenity-layer pivot (no API key needed;
must send User-Agent).

## 5. Composite (proposed — weights are the owner's call)

| Component | Weight | Source | Confidence |
|---|---|---|---|
| Affordability (H+T÷income) | 0.40 | ACS recompute | 6/10 (our estimate) |
| Community Vulnerability | 0.15 | ACS | 6/10 |
| Safety | 0.15 | CPD (existing) | 7/10 |
| Walk | 0.10 | CTA+parks (existing) | 6/10 |
| Displacement | 0.10 | UDP (existing) | 7/10 |
| Vibe | 0.04 | OSM | 6/10 signal |
| Bikeability | 0.03 | OSM | 6/10 signal |
| Runnability | 0.03 | OSM | 6/10 signal |
| **Total** | **1.00** | | |

Composite = weighted sum of the 1–10 sub-scores → normalized 1–10 across 77 CCAs.
Every weight shown on click (hard rule). Composite is never labeled a
recommendation.

## 6. Data-layer changes

### 6a. ACS fetcher (`scripts/fetchers/fetch_acs.py`) — add tables
- B08301 (means of transportation to work → transit_share)
- B25044 (vehicles available per household → autos_per_hh)
- B17001 (poverty)
- Persist already-fetched income_median / vacancy_rate / owner+renter_pct.

### 6b. Migration (NEW — **user applies in Supabase**, REST key can't DDL)
New columns on `tracts` and `ccas`:
`income_median, vacancy_rate, renter_pct, poverty_rate, transit_share,
autos_per_hh, housing_cost_mo, transport_cost_mo, ht_ratio, afford_score,
vuln_score, bike_score, composite_score`
(+ populate existing `vibe_score`, `run_score`).

### 6c. Scoring (`scripts/scoring/`)
- `affordability.py` — H+T model → housing/transport/ratio/afford_score.
- `vulnerability.py` — ACS → vuln_score.
- `lifestyle.py` (or extend) — OSM → vibe/bike/run.
- `composite.py` — weighted blend → composite_score.
All write CCA (+ tract where applicable), idempotent upserts.

### 6d. Read path
Extend gold view / `getCcaById` / `getCityScores` / `getTractById` selects to
include the new columns.

## 7. Frontend changes

- **AreaScores panel** (`src/components/sections/AreaScores.jsx`): add clickable
  rows — Affordability, Vulnerability, (and the H+T breakdown: housing $,
  transport $, AMI, poverty, vacancy, tenure), Vibe, Bikeability, Runnability,
  Composite. Each row: value → source → confidence → caveat (existing `Row`).
- **Map color-by**: dropdown to recolor all 77 CCA polygons by any metric
  (Affordability / Composite / Safety / Walk / Displacement / Vulnerability /
  Vibe / Bike / Run). Clicking a panel score sets the color-by. (This is the
  unbuilt "Color by" feature in CLAUDE.md.)

## 8. Build phases (all before shipping, per decision)

1. ACS fetcher additions + validate output (read-only harness).
2. Migration (user applies) + populate via scoring scripts.
3. Scoring: affordability → vulnerability → lifestyle(OSM) → composite.
4. Read path (gold view + API selects).
5. Frontend: panel rows + map color-by + clickable wiring.
6. End-to-end verify against prod numbers; confidence/caveat copy review.

## 9. Constraints / honesty flags

- Transportation cost is **our simplified model**, not HUD's SEM — label always.
- All new columns need a **user-applied migration** (env has REST key only).
- Quarterly/monthly cron freeze stands; new scoring runs as one-off computes.
- "Dynamic / macro prices" and "over time" are **out of scope v1** (separate
  lower-confidence layer) — LAI itself is a static 5-yr snapshot.

## 10. Open decisions before code

1. Composite weights (§5) — accept or adjust.
2. H+T ratio → 1–10 curve (§2) — accept 30%/60% anchors or specify.
3. Transit/auto cost parameters — confirm I source current CTA pass + AAA/IRS
   per-auto at build and expose them as visible parameters.
