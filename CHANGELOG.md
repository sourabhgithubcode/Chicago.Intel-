# Chicago.Intel — Changelog

All changes documented with data source, confidence impact, and methodology notes.

---

## [2026-06-27] — Live Data Layer, Map Polish & Data-Engineering Showcases

### Added
- Data-engineering tooling showcases — 7 parallel reference implementations of
  the CPD bronze→silver transform, indexed by `DATA_ENGINEERING.md`:
  - `spark/` — PySpark bronze→silver + transformer parity check
  - `processing/` — Polars transform + DuckDB analytics
  - `ingestion/` — dlt Socrata pipeline
  - `validation/` — Great Expectations suite + Pydantic models
  - `airflow/` — DAG for the full pipeline
  - `orchestration_extra/` — Prefect flow, Dask transform, SQLAlchemy models
  - `dbt/` — gold models (address/CCA/tract) + sources + schema tests
- Building amenity score via OpenStreetMap Overpass (free, no API key)
  - 13 categories within 0.25mi (402m), scored by walking distance to nearest place
    (grocery, pharmacy, laundry, transit, cafe, gym, restaurant, park, bank, ATM,
    post office, convenience, hotel); shows the nearest 2 named places per category
  - Grouped weights: Essentials 50% + Lifestyle 30% + Errands 20%
  - `src/lib/api/amenityScore.js`, `AmenityScore.jsx`, treasurer service `/amenities`
- Live address autocomplete via Mapbox Search JS SDK (`SearchBox`) — `SearchBar.jsx`
- Exact building footprint highlight on the map (replaces generic circle)
  - migration 029 `building_footprint_at` RPC + GIST index
- Map style switcher + angled 3D building view (fill-extrusion massing,
  pitch/bearing easing) + smooth boundary fade transitions — `MapView.jsx`
- Geolocation default on load (Chicago bounding-box guard, falls back to the
  address prompt outside it) — `App.jsx`
- Street View building photo + address no-wrap — `BuildingDetail.jsx`
- Why-tooltips explaining scoring methodology on scores

### Changed
- Amenities: Google Places → OpenStreetMap Overpass (free, no key) —
  treasurer service `/amenities` + frontend wrappers
- Amenity empty-state wording: "lookup unavailable" (not "not configured")

### Fixed
- Migration 025: corrected `cpd_incidents.type` — silver load classified crime
  by the IUCR 2-char prefix, dropping ~21% of crime (theft) to 'other' and
  filing aggravated assault as 'property'; reclassified violent/property/other
- Migration 026: anon SELECT (RLS) policies on `ccas` + `tracts` — the anon key
  previously got 0 rows, blanking the CCA card, breadcrumb, displacement, and
  map CCA/tract polygons
- Migration 027: SRID-0 containment bug in the cca/tract/displacement
  containing-point RPCs
- Migration 028: fast `find_building_at` via geometry KNN index (was a slow scan)

### Data Sources
- OpenStreetMap Overpass API (amenity presence/distance) — replaces Google
  Places for the amenity score; distance signal only, not quality/price/hours

---

## [Unreleased] — V2 Real Variable Model

### Added
- Real variable surplus formula replacing MIT Living Wage uniform defaults
  - Google Places price_level integration for grocery and dining cost signals
  - SpotHero / Chicago Data Portal parking cost delta per block
  - Parking: free street permit vs paid garage real monthly rate
- Amenity intelligence layer (16 categories, 0.25mi radius)
  - Grocery, gym, parking, restaurants, coffee, laundry, pet care,
    medical, urgent care, convenience store, liquor store, clothing,
    pharmacy, bank/ATM, park
  - Grouped amenity score: Essential (50%) + Lifestyle (30%) + Cost (20%)
- Composite address score (4-dimension, fully transparent weights)
  - Financial Reality Index 40%
  - Livability Index 30%
  - Stability Index 20%
  - Opportunity Index 10%
- Building-level default view on address search
- Breadcrumb zoom navigation: City › Neighborhood › Street › Building
- Mapbox GL JS interactive map with zoom-driven layer switching
  - Zoom 10–12: CCA polygons
  - Zoom 12–14: Census tract polygons
  - Zoom 14–16: Street segments + building footprints
  - Zoom 16+: Single building + surrounding context
- "Color by" dropdown: Surplus / Safety / Walkability / Displacement / Landlord
- Confidence rating system — every data point labeled 1–10 or "signal"
- "What this does not tell you" section for all scores < 8/10
- Rent override input (user enters listed price → 9/10 confidence)
- Salary slider recalors all map polygons live

### Changed
- Surplus formula: ACS rent + MIT defaults → actual rent + real local costs
- Safety score: CCA polygon aggregation → 0.25mi coordinate radius query
  (confidence: 7/10 → 8/10)

### Data Sources Added
- Google Places API (amenities, price tiers) — 7/10 confidence, signal only
- SpotHero API or Chicago Data Portal (parking rates) — 8/10
- HowLoud API (noise score) — 7/10
- Illinois Report Card API (school ratings) — 8/10
- EPA AirNow API (air quality) — 8/10

---

## [V1.4] — 4-Layer Drill-Down MVP

### Added
- Layer 1: CCA view — 20 neighborhoods, full data sections
- Layer 2: Census tract view — ACS tract-level rent, safety delta vs CCA
- Layer 3: Street block view — coordinate-level CPD query, CTA meters,
  noise, flood zone
- Layer 4: Building intelligence — Cook County Assessor + Chicago 311
- URL parameter passing between layers (sal=, hood=, tract=, street=)
- Breadcrumb navigation across all 4 layers

### Data Sources
- Cook County Assessor: owner, purchase price, tax status, year built
  Confidence: 9/10
- Chicago 311: violations, heat complaints, bed bug reports
  Confidence: 9/10
- FEMA NFHL API: flood zone per coordinate
  Confidence: 9/10
- CTA GTFS: exact stop distance in meters
  Confidence: 9/10

---

## [V1.3] — Chi Hack Night Presentation Build

### Added
- 5-tab dashboard view: Finance / Safety / Walk+Run / Vibe / Displacement
- Interactive map with Leaflet.js + OpenStreetMap tiles
- 30 neighborhoods as colored circle markers
- Salary slider recolors markers live
- Full sidebar with building intelligence panel
- Glassmorphism bento grid design

### Methodology Notes
- Safety: CPD IUCR 5yr average, CCA polygon. Confidence: 7/10
  Caveat: reporting bias — under-policed areas show fewer reports
- Walk score: CTA stop proximity + OSM pedestrian infra. Confidence: 7/10
- Vibe: Yelp API + Park District. Confidence: 6/10. Known North Side bias.
- Displacement: ACS time-series + DePaul IHS. Confidence: 7/10

---

## [V1.2] — Joe Holberg Call Build

### Context
- Call with Joe Holberg (2027 Chicago mayoral candidate, Spring fintech)
- Feedback: commoditization risk on avg rent by location + filter
- Direction: granular geography + real variable costs + authentic analysis

### Changed
- Added displacement risk index design
- Added confidence rating framework (first version)
- Documented "what this does not tell you" principle

### Key Decisions
- Holding non-rent costs constant across neighborhoods is defensible
  as a controlled comparison — but flagged as V1 limitation
- V2 direction: real local cost basket per address

---

## [V1.1] — Capstone Academic Build

### Added
- 6 open-source data layers:
  - ACS rent data (Table B25064, 5-year estimates)
  - CPD crime reports (IUCR categories)
  - CTA GTFS transit data
  - Chicago Park District records
  - OpenStreetMap infrastructure
  - MIT Living Wage Calculator 2024 + IRS 2024 tax brackets
- All 77 Chicago Community Areas (CCAs)
- Real post-tax monthly surplus calculation
- Illinois 4.95% flat tax + FICA 7.65% + federal brackets

### Tax Methodology
- IRS 2024 standard deduction: $14,600 (single)
- Federal brackets: 10/12/22/24% (relevant range for $30k–$200k)
- Illinois: 4.95% flat
- FICA: 7.65% (employee share)
- Confidence: 10/10 — verifiable on any paystub

---

## Methodology Decisions Log

| Decision | Rationale | Confidence Impact |
|----------|-----------|-------------------|
| Non-rent costs held constant across CCAs (V1) | Controlled comparison isolates rent variable | Documents a known limitation, not a flaw |
| CPD safety weighted: violent ×3, property ×1 | Reflects severity differential | Editorial — documented in confidence.js |
| ACS 5-year estimates (2019–23) used for rent | Largest sample, most reliable CCA-level data | Lags market 2–3 years — flagged in UI |
| Tract-level ACS used directionally only | Higher margin of error at smaller geography | 6/10 — shown with MOE warning |
| Google Places price_level shown as signal | Cannot verify precise dollar equivalent | Never shown as exact amount |
| User-entered rent overrides all estimates | User has the real number — highest confidence | 9/10 when user provides actual listed rent |
