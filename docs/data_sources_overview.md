# Chicago.Intel — Data Sources Overview

**Generated:** 2026-05-27
**Snapshot:** live Supabase state
**Companion:** `docs/DATA_DICTIONARY.md` is the deep spec. This file is the quick-reference card — what each source produces, what each column means, and current fill status.

**Totals:** 15 silver tables · 124 columns · 3,912,124 rows · 17 source pipelines.

**Status legend:** ✅ filled · 🟡 partial / has known issues · 🔴 100% NULL or broken

---

## 1. Cook County Assessor → `buildings`  (858,157 rows)

Cook County Property Index Numbers (parcels) — the canonical building identity. `fetch_treasurer` also writes here (enrichment); P2 spatial join from 311 also writes here.

| Column | Meaning | Status |
|---|---|---|
| `pin` | 14-char Cook County PIN, dashed `XX-XX-XXX-XXX-XXXX` — PK | ✅ |
| `address` | Display address from Assessor | ✅ |
| `address_norm` | Normalized address (lowercase, no directionals/units) — join key | ✅ |
| `owner` | Legal owner per Assessor mailing record | ✅ |
| `year_built` | Construction year (NULL if 0 or future) | 🟡 51.6% NULL |
| `purchase_year` | Most recent sale year | 🟡 51.2% NULL |
| `purchase_price` | Most recent sale price ($) | 🟡 51.2% NULL |
| `location` | Parcel centroid POINT(4326) | ✅ |
| `school_elem` | Elementary school name (Assessor field) | ✅ |
| `street_id` | FK to `streets.id` (set by reconcile) | 🔴 100% NULL |
| `landlord_score` | Computed score 0–10 from violations/heat/bugs (not built yet) | 🔴 |
| `tax_current` *(from Treasurer)* | Boolean — owner current on most recent tax year | 🔴 100% NULL |
| `tax_annual` *(from Treasurer)* | Total annual tax bill ($) | 🔴 100% NULL |
| `violations_5yr` *(from P2 enrichment)* | Count of 311 violation SRs within radius, 5yr | 🔴 100% NULL |
| `heat_complaints` *(from P2)* | Count of 311 "No Heat" SRs | 🔴 100% NULL (also blocked on P3) |
| `bug_reports` *(from P2)* | Count of 311 bed bug SRs | 🔴 100% NULL (also blocked on P3) |
| `flood_zone` *(from FEMA NFHL — not built)* | FEMA flood zone code (A/AE/X) | 🔴 100% NULL |
| `flood_zone_at` | Cache timestamp | 🔴 |
| `rent_estimate` *(from Rentcast — not built)* | Estimated monthly rent ($) | 🔴 100% NULL |
| `rent_estimate_at` | Cache timestamp | 🔴 |
| `school_rating` *(from IL Report Card — not built)* | Elementary school rating | 🔴 100% NULL |
| `school_rating_at` | Cache timestamp | 🔴 |
| `updated_at` | Row last-modified timestamp | ✅ |

---

## 2. Census ACS → `tracts`  (1,348 rows)

ACS B25064 (rent), B25003 (tenure), B01003 (population), B19013 (income), B25002 (vacancy) per Census tract. Geometry from separate TIGER fetch.

| Column | Meaning | Status |
|---|---|---|
| `id` | 11-char Census GEOID = `'17031' + tract` — PK | ✅ |
| `cca_id` | FK to `ccas.id`, set by reconcile spatial join | 🟡 41.8% NULL |
| `name` | Tract display name | 🔴 100% NULL (transformer never sets) |
| `rent_median` | B25064_001E — median monthly gross rent ($) | ✅ |
| `rent_moe` | B25064_001M — 90% CI half-width on rent ($) | 🟡 52 rows `-333333333` sentinel |
| `income_median` | B19013 — median household income ($) | ✅ |
| `income_moe` | B19013 MOE | 🟡 25 rows sentinel |
| `population` | B01003_001E — total population (pop-weighted aggregates) | ✅ |
| `vacancy_rate` | B25002 — % housing units vacant | ✅ |
| `owner_occupied_pct` | B25003 derivation | ✅ |
| `renter_occupied_pct` | B25003 derivation | ✅ |
| `safety_score` | Computed from CPD incidents (not built) | 🔴 100% NULL |
| `walk_score` | Computed from amenities/streets (not built) | 🔴 100% NULL |
| `disp_score` | DePaul IHS + ACS time-series → 0–10 displacement risk | 🔴 100% NULL |
| `geometry` | MULTIPOLYGON(4326) — TIGER tract boundary | 🟡 40.6% NULL |
| `data_vintage` | e.g. `'2019-23'` | ✅ |
| `updated_at` | Row timestamp | ✅ |

---

## 3. Chicago portal `igwz-8jzy` → `ccas`  (77 rows)

77 Community Areas — Chicago's neighborhood layer. Scores roll up from `tracts` (population-weighted).

| Column | Meaning | Status |
|---|---|---|
| `id` | 1–77 CCA number — PK | ✅ |
| `name` | Community Area name (e.g. "Rogers Park") | ✅ |
| `rent_median` | Pop-weighted avg of contained tracts | 🔴 NULL (rollup not run) |
| `safety_score` | Composite from CPD incidents | 🔴 NULL |
| `walk_score` | Composite | 🔴 NULL |
| `run_score` | Personalization placeholder | 🔴 NULL |
| `vibe_score` | Yelp-based vibe (not built) | 🔴 NULL |
| `disp_score` | Pop-weighted from tracts | 🔴 NULL |
| `geometry` | MULTIPOLYGON(4326) — CCA boundary | ✅ |
| `data_vintage` | e.g. `'2019-23'` | ✅ |
| `updated_at` | Timestamp | ✅ |

---

## 4. Chicago GIS building footprints → `building_footprints`  (820,598 rows)

Building outline polygons (City GIS keyspace — cannot FK to `buildings.pin`; spatial join only).

| Column | Meaning | Status |
|---|---|---|
| `bldg_id` | City GIS building ID — PK (one `bldg_id=0` sentinel exists) | ✅ |
| `geometry` | MULTIPOLYGON(4326) — building footprint | ✅ |

---

## 5. CPD Socrata `ijzp-q8t2` → `cpd_incidents`  (1,471,413 rows)

Crime incidents. Coordinates redacted by CPD to nearest block centroid + 4-hour bucket (privacy, not error). Confidence 7/10.

| Column | Meaning | Status |
|---|---|---|
| `id` | Internal id | ✅ |
| `iucr` | 4-char Illinois Uniform Crime Reporting code | ✅ |
| `type` | Derived: `'violent'` or `'property'` per IUCR bucket | ✅ |
| `date` | Incident date (TIMESTAMPTZ) | 🟡 data 25 days stale, span 6.3yr vs 5yr spec |
| `location` | POINT(4326) — redacted to block | ✅ |
| `year` | Year extracted from date | ✅ |

---

## 6. Chicago 311 Socrata `v6vf-nfxy` → `complaints_311`  (454,227 rows)

Service requests. Currently only 2 types fetched (Rodent + Building Violation); heat + bed bug needed for P3.

| Column | Meaning | Status |
|---|---|---|
| `id` | sr_number — natural key | ✅ |
| `type` | Service request type | 🟡 only 2 types fetched |
| `address` | Filer-provided address | ✅ |
| `date` | Created date | ✅ |
| `location` | POINT(4326) | ✅ |
| `address_norm` | Normalized join key for `buildings` | 🔴 100% NULL (transformer never sets — P4) |

---

## 7. Chicago building permits Socrata → `building_permits`  (226,114 rows)

Permits issued by Department of Buildings. Most permits don't carry a PIN (City limitation).

| Column | Meaning | Status |
|---|---|---|
| `id` | Permit number — PK | ✅ |
| `permit_type` | Raw permit type (6 distinct values) | ✅ |
| `category` | Bucketed: residential/commercial/electric/etc | 🟡 75.4% "other" (P5) |
| `issue_date` | When city issued the permit | ✅ |
| `applied_at` | When application filed | ✅ |
| `pin` | Cook County PIN (not in source) | 🔴 100% NULL (expected) |
| `address` | Permit job address | ✅ |
| `address_norm` | Normalized join key | ✅ |
| `reported_cost` | Self-reported job cost ($) | 🟡 11 rows >$500M, $1.93B outlier |
| `permit_fee` | City fee charged | ✅ |
| `location` | POINT(4326) | 🟡 4,106 NULL |

---

## 8. Chicago street centerlines GIS → `streets`  (55,872 rows)

Street segments — one row per centerline between two intersections.

| Column | Meaning | Status |
|---|---|---|
| `id` | Segment ID — PK | ✅ |
| `name` | Full street name (e.g. "W BELMONT AVE") | ✅ |
| `name_norm` | Normalized for matching | ✅ |
| `from_addr` | Lower address in segment range | 🟡 95 are 0; 2 inverted |
| `to_addr` | Upper address in segment range | 🟡 same |
| `cca_id` | FK to `ccas.id` (reconcile) | 🔴 100% NULL |
| `tract_id` | FK to `tracts.id` (reconcile) | 🔴 100% NULL |
| `geometry` | Declared MULTILINESTRING but returns LINESTRING | 🟡 migration 022 unapplied? |

---

## 9. CTA GTFS `stops.txt` → `cta_stops`  (10,833 rows)

Individual stop platforms (not stations). Read from CTA GTFS zip.

| Column | Meaning | Status |
|---|---|---|
| `id` | stop_id from GTFS | ✅ |
| `name` | Stop display name | ✅ |
| `lines` | Routes serving this stop (joined from routes.txt) | 🔴 empty array on all rows (V1 stub) |
| `accessible` | wheelchair_boarding from GTFS | ✅ 99.1% true |
| `location` | POINT(4326) | ✅ |

---

## 10. Park District GIS → `parks`  (614 rows)

Chicago Park District park boundaries.

| Column | Meaning | Status |
|---|---|---|
| `id` | Park ID — PK | ✅ |
| `name` | Park name | ✅ |
| `acreage` | Park size in acres | ✅ |
| `location` | POINT(4326) — park centroid | ✅ |
| `boundary` | MULTIPOLYGON(4326) — park outline | ✅ |

---

## 11. Chicago parking permit zones `u9xt-hiju` → `parking_permit_zones`  (10,372 rows)

Residential parking permit zones — text-only, no geometry. One row per street-segment side.

| Column | Meaning | Status |
|---|---|---|
| `id` | Row ID — PK | ✅ |
| `zone` | Permit zone number (e.g. 383) | ✅ |
| `street_name` | Street name | ✅ |
| `street_direction` | N/S/E/W prefix | ✅ |
| `street_type` | AVE/ST/BLVD/etc | ✅ |
| `address_low` | Lower address bound | ✅ |
| `address_high` | Upper address bound | ✅ |
| `odd_even` | Even/Odd/Both/NULL side | ✅ |
| `ward` | City ward number (1–50) | 🔴 163 invalid (142 ward=0, 21 NULL) |
| `status` | Active / inactive | ✅ 95.2% active |

---

## 12. CPS elementary boundaries GIS → `school_boundaries`  (353 rows)

Chicago Public Schools elementary attendance zone polygons.

| Column | Meaning | Status |
|---|---|---|
| `school_id` | CPS school ID — PK | ✅ |
| `rcdts` | IL state school code | 🔴 100% NULL (by design) |
| `school_name` | School name | ✅ |
| `grade_category` | "Elementary" (all rows) | ✅ |
| `school_year` | e.g. "2023-2024" | ✅ |
| `boundary` | MULTIPOLYGON(4326) — attendance zone | ✅ |

---

## 13. Chicago snow route restrictions `i6k4-giaj` → `snow_route_restrictions`  (144 rows)

Streets restricted during 2-inch snowfall — no parking after snow.

| Column | Meaning | Status |
|---|---|---|
| `id` | Row ID — PK (ids 1–165 with 21 gaps) | ✅ |
| `on_street` | Street with restriction | ✅ |
| `from_street` | Restriction start cross-street | 🟡 1 row NULL |
| `to_street` | Restriction end cross-street | 🟡 1 row NULL |
| `restriction_type` | All "2 INCH" | ✅ |
| `geometry` | MULTILINESTRING(4326) | ✅ |

---

## 14. Chicago winter overnight restrictions `mcad-r2g5` → `winter_overnight_restrictions`  (20 rows)

Streets with overnight winter parking ban.

| Column | Meaning | Status |
|---|---|---|
| `id` | Row ID — PK (ids 45–138) | ✅ |
| `on_street` | Street with restriction | ✅ |
| `from_street` | Restriction start | ✅ |
| `to_street` | Restriction end | ✅ |
| `restriction_type` | All "OVERNIGHT" | ✅ |
| `geometry` | MULTILINESTRING(4326) | ✅ |

---

## 15. DePaul Institute for Housing Studies → `displacement_typology`  (1,982 rows)

Neighborhood Change Typology — 11 categories of displacement / gentrification by tract.

| Column | Meaning | Status |
|---|---|---|
| `geoid` | 11-char Census GEOID — PK | ✅ |
| `typology` | One of 11 labels (e.g. "At Risk of Becoming Exclusive") | ✅ |

679 / 1,982 geoids don't match `tracts.id` — confirmed as DuPage/Lake/Will/Kane/McHenry/Kendall + 15 suburban Cook tracts (FIPS-validated).

---

## Pure-enrichment sources (no new table)

| Source | Writes to | Status |
|---|---|---|
| `load_tract_geometry` (Census TIGER) | `tracts.geometry` | 🟡 40.6% NULL |
| `fetch_treasurer` (Cook Co Treasurer) | `buildings.tax_current`, `buildings.tax_annual` | 🔴 100% NULL |

---

## Cross-reference

- Deep spec: `docs/DATA_DICTIONARY.md` (2841 lines — sections 13.1–13.29 have raw→silver field mappings)
- Audit baseline: `docs/silver_layer_audit.md` (2026-05-15 snapshot — partially stale)
- Per-table refreshed audits: `docs/dq/<table>.md` (2026-05-27, 15 files)
- Project rules: `CLAUDE.md`
