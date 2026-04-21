# Chicago.Intel — Claude Code Instructions

## Project Overview

Chicago.Intel is a neighborhood intelligence dashboard for Chicago renters.
Core value: user enters an address + salary → sees real post-tax monthly
surplus with building-level intelligence, amenity data, and zoom-out context
to street, neighborhood, and city level.

**Philosophy:** Show what data says. Show the source. Show confidence.
Let the user decide. Never tell someone where to live.

---

## Architecture

### Stack
- **Frontend:** React + Vite + Tailwind CSS + Mapbox GL JS
- **Backend:** Supabase (PostgreSQL + PostGIS)
- **Hosting:** Render (frontend static site + Python cron) + Supabase (free tier)
- **APIs:** Google Places, Google Maps Geocoding, FEMA NFHL, CTA GTFS
- **Analytics:** GoatCounter

### Environment Variables
```
VITE_SUPABASE_URL
VITE_SUPABASE_ANON_KEY
VITE_GOOGLE_MAPS_KEY        # domain-restricted
VITE_GOOGLE_PLACES_KEY      # domain-restricted
VITE_RENTCAST_KEY           # optional — $49/mo
VITE_HOWLOUD_KEY            # optional — $0.05/query
VITE_MAPBOX_TOKEN
```

---

## Core Formula — Never Change Without Documenting

```
Real Surplus = Take-home
             - Actual rent (user-entered or Rentcast estimate)
             - Real grocery cost (Google Places price_level × baseline delta)
             - Real dining cost (nearby avg price_level × frequency)
             - Transit cost (CTA pass or car cost by location)
             - Parking delta (free street vs paid garage — real monthly rate)
             - Healthcare OOP (MIT Living Wage default, user-adjustable)
             - Lifestyle (user-adjustable)
             - Savings goal (user-adjustable)
```

### Tax Engine (IRS 2024 — do not modify without updating source)
```javascript
// src/lib/taxEngine.js
// Source: IRS Publication 15-T 2024, Illinois DOR, SSA
// Confidence: 10/10 — exact law
// Standard deduction: $14,600 (single filer 2024)
// Federal brackets: 10/12/22/24/32/35/37%
// Illinois flat rate: 4.95%
// FICA: 7.65% (SS 6.2% + Medicare 1.45%)
```

---

## Confidence Rating System

Every data point in the UI must carry a confidence rating.
This is non-negotiable — it is the core trust mechanism of the product.

| Rating | Meaning | Example |
|--------|---------|---------|
| 9–10/10 | Verifiable in under 5 min | Tax calc, Cook County Assessor |
| 7–8/10 | Strong source, minor caveats | CPD crimes, ACS CCA rent |
| 6/10 | Directional signal only | Tract-level ACS, Yelp vibe |
| Signal | Not a measurement | Google Places price_level |

### Rules
- Never display a number without its source and confidence
- If confidence < 7/10, always show "What this does not tell you"
- Price tier signals (Google Places $/$$/$$$/$$$$) must NEVER be
  converted to precise dollar amounts without a citable source
- Show "$85/mo estimate" not "$85/mo" for cost deltas from price tiers

---

## Data Sources & Confidence Reference

| Source | Data | Confidence | Refresh |
|--------|------|------------|---------|
| IRS 2024 + IL DOR + FICA | Tax calculation | 10/10 | Annual |
| Cook County Assessor | Owner, purchase price, tax status | 9/10 | Annual |
| Chicago Data Portal / 311 | Violations, heat, bed bugs | 9/10 | Live |
| CTA GTFS | Stop coordinates | 9/10 | Quarterly |
| FEMA NFHL API | Flood zones | 9/10 | As updated |
| ACS B25064 2019–23 | CCA median rent | 8/10 | 5yr rolling |
| CPD IUCR 2019–23 | Crime incidents w/ lat/lng | 7/10 | Annual |
| Google Places price_level | Grocery/dining tier | 7/10 (signal) | Cache 30d |
| ACS tract-level | Tract rent (higher MOE) | 6/10 | 5yr rolling |
| DePaul IHS + ACS time-series | Displacement risk | 7/10 | Annual |
| HowLoud API | Noise score | 7/10 | Static |
| Yelp API | Vibe/lifestyle | 6/10 (N. Side bias) | Cache 7d |

---

## Database Schema (Supabase / PostGIS)

### Key Tables
- `ccas` — 77 Community Areas with geometry + scores
- `tracts` — ~800 census tracts with geometry
- `buildings` — Cook County Assessor parcel data
- `cpd_incidents` — 300K+ incidents with GIST index on location
- `complaints_311` — Building violations, heat, bed bugs
- `cta_stops` — All CTA stops with GIST index
- `parks` — Park District GIS data
- `amenities_cache` — Google Places results cached per address

### Critical Indexes (never remove)
```sql
CREATE INDEX ON cpd_incidents USING GIST(location);
CREATE INDEX ON buildings USING GIST(location);
CREATE INDEX ON buildings(address);
CREATE INDEX ON cta_stops USING GIST(location);
```

### Key Query Patterns

**Safety radius (0.25mi = 402 meters):**
```sql
SELECT COUNT(*) FILTER (WHERE type='violent') as violent,
       COUNT(*) FILTER (WHERE type='property') as property
FROM cpd_incidents
WHERE ST_DWithin(location, ST_MakePoint($lng,$lat)::geography, 402)
AND date >= NOW() - INTERVAL '5 years';
```

**Nearest CTA stop:**
```sql
SELECT name, lines,
  ST_Distance(location, ST_MakePoint($lng,$lat)::geography) as meters
FROM cta_stops
ORDER BY location <-> ST_MakePoint($lng,$lat)::geography
LIMIT 1;
```

---

## UI Rules — Non-Negotiable

### Default View
- Building level is ALWAYS the default after address search
- Breadcrumb always shows: Chicago › Neighborhood › Street › Address
- User zooms OUT via breadcrumb — never forced to start at city level

### Data Display
- Every collapsible section shows: score/signal → source → confidence → caveats
- "What this does not tell you" must appear for any score < 8/10
- Composite scores must show all component weights
- Price tier signals labeled: "$$$ (premium tier) — signal, not precise amount"

### Surplus Formula Visibility
- Formula breakdown always visible in building view (not hidden)
- Each line item shows its data source on hover
- Sliders for all user-adjustable costs
- Rent override input always available with label:
  "Enter listed rent for highest accuracy (9/10 confidence)"

### Map Behavior
- Mapbox GL JS — vector tiles
- Zoom 10–12: CCA polygons
- Zoom 12–14: Census tract polygons
- Zoom 14–16: Street segments + building footprints
- Zoom 16+: Single building highlight + surrounding context
- "Color by" dropdown: Surplus / Safety / Walkability / Displacement / Landlord
- Salary slider recolors all polygons live

---

## Amenity Layer (Building View)

16 categories queried via Google Places API within 0.25mi:
grocery, gym, parking (free + paid), restaurants, coffee, laundry,
pet care, medical, urgent care, convenience store, liquor store,
clothing, pharmacy, bank/ATM, park

### Amenity Score Weights
```
Essential access:    50% (grocery, pharmacy, urgent care, laundry)
Lifestyle density:   30% (restaurants, coffee, fitness, park)
Cost efficiency:     20% (grocery tier, dining tier, parking delta)
```

### Cost Delta Rules
- Grocery price delta: signal only unless sourced from actual price data
- Parking: real monthly rate from SpotHero API or Chicago Data Portal
- Label ALL cost estimates: "~$X/mo estimate · signal from price tier"

---

## Composite Address Score

```
Financial Reality Index:  40% weight
Livability Index:         30% weight
Stability Index:          20% weight
Opportunity Index:        10% weight
```

All weights documented in `src/lib/confidence.js`.
User can view raw component scores without the composite.
Never present composite score as a recommendation.

---

## What the Tool Must Never Do

- Say "This is a safe neighborhood" → say CPD data + confidence + caveats
- Say "We recommend X" → show data, let user decide
- Convert Google Places price_level to precise $ without a citable source
- Show a composite score without explaining every component weight
- Display a number without its source
- Hide methodology behind a black box

---

## Permanent UI Copy (do not change)

> "Chicago.Intel shows you what public data says about any address in
> Chicago. We tell you how confident we are in each number and what it
> does not capture. You make the decision. We never tell you where to live."

---

## Data Pipeline Scripts (run quarterly)

```
scripts/
  fetch_acs.py          # Census API — ACS B25064, B25003, B01003
  fetch_cpd.py          # Chicago Data Portal Socrata — crimes
  fetch_assessor.py     # Cook County Assessor bulk CSV + Treasurer
  fetch_311.py          # Building violations, heat complaints, bed bugs
  fetch_cta.py          # CTA GTFS stops.txt
  fetch_parks.py        # Park District GIS polygons
  fetch_fema.py         # FEMA NFHL — called live, not bulk
  seed_supabase.py      # Load all processed data to Supabase
```

All scripts write to `/data/processed/` before loading to Supabase.
Never load raw API responses directly to production tables.

---

## Changelog

See CHANGELOG.md for version history.
