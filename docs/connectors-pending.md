# Pending live-API connectors

Five live per-address connectors from CLAUDE.md are queued behind API
keys you haven't signed up for yet. This doc captures the contract for
each so the actual Flask routes + cache tables + frontend wrappers can
be wired quickly (~30 min each) once a key arrives.

**Built shape (today):** `chicago-intel-treasurer` Flask service on
Render hosts every live proxy. Routes follow the same pattern:
GET param → cache check → upstream API → cache write → return.
Frontend wrapper in `src/lib/api/<name>.js` matches the shape of
`flood.js` / `treasurer.js`.

**Add each when its UI section is also being built** — same no-bloat
rule we've been following all session. The exception today (FEMA)
was justified by an explicit user override; future ones aren't.

---

## 1. Google Places (grocery/dining tier signal)

| Field | Value |
|---|---|
| Endpoint | `https://maps.googleapis.com/maps/api/place/nearbysearch/json` |
| Auth | API key in URL (`key=`) |
| Free tier | $200/mo credit, ~10K Nearby Search calls |
| Signup | Google Cloud Console → enable Places API → create key |
| Env var | `GOOGLE_PLACES_KEY` (backend, NOT VITE_) |
| Cache table | `amenities_cache` (already exists, migration 001) |
| Cache TTL | 30d |
| CORS | supports CORS, but proxy anyway for cache + key isolation |
| Request shape | `lat,lng,type` (grocery/restaurant/etc) |
| Response | array of `{name, price_level, vicinity, place_id}` |

UI section it unblocks: **Amenities** (16 categories within 0.25mi).

---

## 2. Yelp Fusion (vibe/lifestyle)

| Field | Value |
|---|---|
| Endpoint | `https://api.yelp.com/v3/businesses/search` |
| Auth | Bearer API key |
| Free tier | 5,000 calls/day |
| Signup | yelp.com/developers → Create App |
| Env var | `YELP_API_KEY` (backend) |
| Cache table | `amenities_cache` (shared with Google Places — distinguish by `source` column) |
| Cache TTL | 7d |
| CORS | no CORS, **must proxy** |
| Request shape | `lat,lng,categories,radius` |
| Response | array of `{name, rating, price, categories}` |

UI section it unblocks: **Lifestyle / Vibe**.

Caveat from CLAUDE.md: Yelp is North-Side-biased — confidence 6/10.

---

## 3. AirNow (real-time AQI)

| Field | Value |
|---|---|
| Endpoint | `https://www.airnowapi.org/aq/observation/zipCode/current/` |
| Auth | API key in URL (`API_KEY=`) |
| Free tier | unlimited (free signup) |
| Signup | docs.airnowapi.org → Request API Key |
| Env var | `AIRNOW_API_KEY` (backend) |
| Cache table | `aqi_cache` — new migration: `(zip_code TEXT PK, aqi INT, category TEXT, fetched_at TIMESTAMPTZ)` |
| Cache TTL | 1h |
| CORS | no CORS, **must proxy** |
| Request shape | ZIP code (frontend derives from building address) |
| Response | `{AQI, Category, ParameterName, DateObserved}` |

UI section it unblocks: **Air Quality** subsection of the Building view.

---

## 4. HowLoud (noise score)

| Field | Value |
|---|---|
| Endpoint | `https://howloud.com/score/<address>` (proprietary) |
| Auth | API key in header |
| Free tier | none, $0.05/query |
| Signup | howloud.com — contact sales |
| Env var | `HOWLOUD_API_KEY` (backend) |
| Cache table | `noise_cache` — new migration: `(address_key TEXT PK, score INT, category TEXT, fetched_at)` |
| Cache TTL | 1yr (noise data is essentially static) |
| CORS | unverified |
| Request shape | full street address |
| Response | `{score, category}` |

UI section it unblocks: **Noise** signal in Building view.

**Cost risk:** per-query pricing. Should be gated by user toggle so
casual browsing doesn't burn $.

---

## 5. RentCast (rent estimate)

| Field | Value |
|---|---|
| Endpoint | `https://api.rentcast.io/v1/avm/rent/long-term` |
| Auth | API key in header (`X-Api-Key`) |
| Free tier | none |
| Paid tier | $49/mo (verify on rentcast.io — pricing changes) |
| Signup | rentcast.io → Developer Plans |
| Env var | `RENTCAST_API_KEY` (backend) |
| Cache table | `rent_estimate_cache` — new migration: `(pin TEXT PK, estimate INT, range_low INT, range_high INT, fetched_at)` |
| Cache TTL | 30d |
| CORS | unverified — assume proxy |
| Request shape | address + bedroom count |
| Response | `{rent, rentRangeLow, rentRangeHigh}` |

UI section it unblocks: **Rent estimate fallback** when user hasn't
entered an actual listed rent.

**Cost risk:** monthly subscription regardless of usage. Defer until
real users justify it.

---

## Illinois Report Card — NOT a live connector

CLAUDE.md originally listed Illinois Report Card alongside the live
APIs. Verified during research: ISBE publishes school data via
SharePoint with annual CSV downloads, no live REST API. Wrong shape
for the per-address pattern.

Right home: bulk ingest. Add as a fetcher in `scripts/fetchers/fetch_illinois_schools.py`
that pulls the annual CSV → silver `schools` table → join to
`buildings.school_elem` for school metadata (ratings, scores, demographics).

Defer until a UI section actually consumes school details beyond the
name we already have on `buildings`.
