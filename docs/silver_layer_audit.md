# Silver Layer — Data Quality Audit & EDA
**Generated:** 2026-05-15  
**Bronze load date:** 2026-05-10 to 2026-05-12  
**Total silver tables:** 16  
**Total rows across all tables:** ~3.9M+

---

## Table Inventory

| Table | Rows | Size | Source |
|---|---|---|---|
| `cpd_incidents` | 1,471,413 | 434 MB | CPD Socrata |
| `buildings` | 858,157 | 357 MB | Cook County Assessor (4 datasets) |
| `building_footprints` | 820,598 | 212 MB | City of Chicago GIS |
| `complaints_311` | 454,227 | 143 MB | City 311 Socrata |
| `building_permits` | 226,114 | 68 MB | City permits Socrata |
| `streets` | 55,872 | 33 MB | City centerlines GIS |
| `tracts` | 1,348 | 4 MB | ACS 2019–23 + Census geometry |
| `cta_stops` | 10,833 | 3.6 MB | CTA GTFS |
| `parking_permit_zones` | 10,372 | — | City parking zones |
| `school_boundaries` | 353 | 2.1 MB | CPS boundaries GIS |
| `parks` | 614 | 1.9 MB | Park District GIS |
| `snow_route_restrictions` | 144 | 792 KB | City snow routes GIS |
| `displacement_typology` | 1,982 | 472 KB | DePaul IHS |
| `winter_overnight_restrictions` | 20 | 200 KB | City parking restrictions GIS |
| `ccas` | 77 | 40 KB | Seeded manually |
| `school_boundaries` | 353 | 2.1 MB | CPS GIS |

---

## Data Quality Audit
 
### 🔴 Critical — Blocking for production

| Issue | Table | Affected | Root Cause |
|---|---|---|---|
| `violations_5yr`, `heat_complaints`, `bug_reports` all 0 | buildings | 858,157 (100%) | 311→buildings join/reconcile never ran |
| `tax_current`, `tax_annual` all NULL | buildings | 858,157 (100%) | Treasurer enrichment never ran |
| `street_id` all NULL | buildings | 858,157 (100%) | Reconcile script never ran |
| `flood_zone` all NULL | buildings | 858,157 (100%) | Live FEMA only — no batch enrichment |
| `cca_id` all NULL | tracts | 1,348 (100%) | Reconcile script never ran |
| `cca_id`, `tract_id` all NULL | streets | 55,872 (100%) | Reconcile script never ran |
| `geometry` all NULL | ccas | 77 (100%) | No bronze source — CCA geometries never loaded |
| `disp_score`, `safety_score` all NULL | tracts | 1,348 (100%) | Score computation never ran |

**Impact:** Gold materialized views (`gold_address_intel`, `gold_cca_summary`, `gold_tract_summary`) will be incomplete or broken until reconcile runs and CCA geometries are loaded.

### 🟠 High — Data gaps

| Issue | Table | Affected | Notes |
|---|---|---|---|
| `geometry` 40.6% NULL | tracts | 547/1,348 | ACS has 1,348 tracts; tract_geometry bronze only covers 801 |
| `address_norm` 100% NULL | complaints_311 | 454,227 | Transformer never computes it |
| `pin` 100% NULL | building_permits | 226,114 | Not in source data — expected |
| `category = 'other'` 75.4% | building_permits | 170,408 | "Express Permit", "Easy Permit" etc. unclassified |
| 679 unmatched geoids | displacement_typology | 34.3% | Likely suburban Cook County tracts |
| `year_built` 51.6% NULL | buildings | 442,795 | Assessor source gap — expected |
| `purchase_year/price` 51.2% NULL | buildings | 439,287 | Only arm's-length sales recorded |

### 🟡 Medium — Needs investigation

| Issue | Table | Count | Notes |
|---|---|---|---|
| `null_location` | building_permits | 4,106 (1.8%) | Can't place on map |
| `year_built < 1850` | buildings | 7 | Suspicious — Chicago founded 1833 |
| `max purchase_price = $850M` | buildings | 1 | Extreme outlier |
| `max permit_cost = $1.934B` | building_permits | 1 | Extreme outlier |
| Zero address range streets | streets | 95 | Alleys/unnamed segments |
| Inverted address ranges | streets | 2 | `from_addr > to_addr` |
| Only 2 complaint types | complaints_311 | — | Fetch filtered to rodent + building violation only |
| `ward = 0` | parking_permit_zones | 21 rows | Invalid ward number |

### ✅ Clean — No issues

| Check | Result |
|---|---|
| Duplicate PKs | 0 across all 7 key tables |
| Out-of-bbox coordinates | 0 across buildings, CPD, 311, permits |
| CPD nulls | 0 on all columns |
| Parks nulls | 0 on all columns |
| CTA stops nulls | 0 on all columns |
| School boundaries | Clean |
| Building footprints | 8 dropped / 820,606 (0.001%) |

---

## Exploratory Data Analysis

### buildings (858,157 rows)

**Year built distribution (415,362 known):**
| Era | Count | % |
|---|---|---|
| Pre-1900 | 66,375 | 16.0% |
| 1900–1919 | 91,112 | 21.9% |
| 1920–1939 | 89,378 | 21.5% |
| 1940–1959 | 99,023 | 23.8% |
| 1960–1979 | 35,658 | 8.6% |
| 1980–1999 | 14,064 | 3.4% |
| 2000–2009 | 12,435 | 3.0% |
| 2010+ | 7,317 | 1.8% |

**Key insight:** 83% of buildings built before 1960. Chicago has one of the oldest urban housing stocks in the US.

**Purchase price distribution (418,870 with sales data):**
| Metric | Value |
|---|---|
| Min | $10,050 |
| Median | $300,000 |
| P75 | $504,500 |
| P95 | $1,840,000 |
| Max | $850,000,000 |
| Under $100K | 53,060 (12.7%) |
| $100K–$500K | 262,585 (62.7%) |
| Over $1M | 39,844 (9.5%) |

**Other flags:**
- 51,790 corporate owners (LLC/Trust) — 6%
- 528 properties with purchase_price > $100M

---

### cpd_incidents (1,471,413 rows)

**By year:**
| Year | Total | Violent | Property | Other | Violent % |
|---|---|---|---|---|---|
| 2020 | 207,973 | 51,563 | 36,872 | 119,538 | 24.8% |
| 2021 | 202,869 | 50,690 | 37,697 | 114,482 | 25.0% |
| 2022 | 234,881 | 52,314 | 50,123 | 132,444 | 22.3% |
| 2023 | 261,245 | 57,820 | 59,703 | 143,722 | 22.1% |
| 2024 | 257,530 | 57,721 | 56,208 | 143,601 | 22.4% |
| 2025 | 235,760 | 50,761 | 54,770 | 130,229 | 21.5% |
| 2026 | 71,155 | 15,217 | 17,992 | 37,946 | 21.4% |

- Date range: 2020-01-01 → 2026-05-02
- 369 distinct IUCR codes
- Geography: perfectly within Chicago bbox, 0 nulls

---

### complaints_311 (454,227 rows)

| Type | Count | % |
|---|---|---|
| Rodent Baiting/Rat Complaint | 318,358 | 70.0% |
| Building Violation | 135,869 | 30.0% |

- Date range: 2020-01-01 → 2026-05-09
- Only 2 types fetched — intentional filter in `fetch_311.py`
- **Gap:** heat complaints and bed bug reports are missing — needed for `buildings.heat_complaints` and `buildings.bug_reports`

---

### tracts (1,348 rows)

**Rent distribution (1,288 with data):**
| Metric | Value |
|---|---|
| Min | $343 |
| P10 | $984 |
| P25 | $1,147 |
| Median | $1,350 |
| P75 | $1,700 |
| P90 | $2,135 |
| Max | $3,501 |
| Avg | $1,463 |
| StdDev | $485 |

Buckets: <$700: 24 tracts | $700–$1K: 127 | $1K–$1.5K: 677 | $1.5K–$2K: 298 | >$2K: 168

**Income distribution (1,317 with data):**
| Metric | Value |
|---|---|
| Min | $13,489 |
| P25 | $56,460 |
| Median | $78,064 |
| P75 | $105,982 |
| Max | $250,001+ |
| Poverty (<$30K) | 60 tracts |
| Working class ($30K–$60K) | 321 tracts |
| Middle class ($60K–$100K) | 556 tracts |
| High income (>$100K) | 382 tracts |

Other metrics: avg vacancy 8.6% | avg renter-occupied 42.9% | avg owner-occupied 57.1%

---

### building_permits (226,114 rows)

**By year:**
| Year | Permits | New Construction | Renovation | Demolition | Other | Avg Cost |
|---|---|---|---|---|---|---|
| 2020 | 38,512 | 1,145 | 7,443 | 738 | 29,186 | $221K |
| 2021 | 39,124 | 1,469 | 7,311 | 888 | 29,456 | $232K |
| 2022 | 38,336 | 1,590 | 7,755 | 785 | 28,206 | $287K |
| 2023 | 34,389 | 1,224 | 6,428 | 615 | 26,122 | $224K |
| 2024 | 33,442 | 1,246 | 6,184 | 635 | 25,377 | $303K |
| 2025 | 32,044 | 1,460 | 5,507 | 673 | 24,404 | $300K |
| 2026 | 10,267 | 483 | 1,901 | 226 | 7,657 | $591K |

- Median permit cost: $10,000 | Max: $1.934B
- Declining permit volume 2022→2025 — construction slowdown signal
- 75.4% "other" category — classification needs expansion

---

### displacement_typology (1,982 rows)

| Typology | Count | % |
|---|---|---|
| At Risk of Becoming Exclusive | 593 | 29.9% |
| Stable Moderate/Mixed Income | 405 | 20.4% |
| Low-Income/Susceptible to Displacement | 329 | 16.6% |
| Stable/Advanced Exclusive | 189 | 9.5% |
| At Risk of Gentrification | 175 | 8.8% |
| Advanced Gentrification | 93 | 4.7% |
| Ongoing Displacement | 83 | 4.2% |
| Early/Ongoing Gentrification | 46 | 2.3% |
| Becoming Exclusive | 38 | 1.9% |
| High Student Population | 26 | 1.3% |
| Unavailable or Unreliable Data | 5 | 0.3% |

- 1,303 geoids matched to tracts table (65.7%)
- 679 unmatched (34.3%) — likely suburban Cook County

---

### parking_permit_zones (10,372 rows)

- 2,048 unique permit zones across 771 unique streets
- 9,876 active (95.2%) | 496 inactive/null (4.8%)
- 0 null zones, 21 null/zero wards (invalid)
- Even side: 5,185 | Odd side: 5,187 | Both sides: 0
- Wards covered: 1–50 (51 distinct values including ward=0 anomaly)
- No geometry — text-only (street name, address range, zone)
- Top zones by segment count: 383 (655), 143 (531), 102 (235)

---

### snow_route_restrictions (144 rows)

- 125 unique streets covered
- All 144 rows have restriction_type = "2 INCH" (uniform)
- 1 row missing from_street / to_street
- 0 null geometry — all have MultiLineString geometry
- IDs 1–165 (non-contiguous — some filtered at source)

---

### winter_overnight_restrictions (20 rows)

- 19 unique streets
- All 20 rows have restriction_type = "OVERNIGHT" (uniform)
- 0 nulls on any field
- IDs 45–138 (subset of city-wide restriction dataset)

---

### cta_stops (10,833 rows)

- 99.1% accessible (10,734/10,833)
- 0 nulls on location, name, accessible
- Geo bounds: lat 41.644–42.023 (within Chicago ✓)
- Note: 10,833 is individual stop platforms, not stations

---

## Action Items (Priority Order)

### P0 — Run reconcile script
Populates `buildings.street_id`, `tracts.cca_id`, `streets.cca_id/tract_id`. Gold layer is broken without this.

### P1 — Load CCA geometries
`ccas.geometry` is 100% null. Gold map layer broken. Need to fetch CCA boundaries from Chicago Data Portal or ArcGIS.

### P2 — Fix complaints_311 → buildings enrichment
`violations_5yr`, `heat_complaints`, `bug_reports` all zero. Need the reconcile to spatially join 311 to buildings within radius.

### P3 — Fetch heat + bed bug 311 types
Currently only "Rodent" and "Building Violation" fetched. `fetch_311.py` needs to also pull heat complaints and bed bug reports for the buildings enrichment to work.

### P4 — Fix `complaints_311.address_norm`
Transformer (`_311.py`) never computes `address_norm`. One-line fix: same normalization as other transformers.

### P5 — Expand building_permits category classification
75.4% fall into "other". "Express Permit", "Easy Permit", "Sign", "Electric", "Plumbing", "Scaffold" should each be their own category — requires a migration to add values to the CHECK constraint.

### P6 — Investigate tract geometry gap
547 tracts have no geometry. Source was Census TIGER 2010 (geoid10). ACS uses 2020 TIGER geoids — possible vintage mismatch. Fetch 2020 TIGER tract geometries.
