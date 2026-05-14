# My Knowledge

---

## Data Sources

### Live API — called per address query, results cached in Supabase

These fire when a user searches an address. The Flask proxy (`treasurer_service.py`) handles all of them and caches results so the same address doesn't trigger a repeat paid call.

| Source | Route | Cache TTL | Cache Table |
|--------|-------|-----------|-------------|
| Cook County Treasurer | `/treasurer-lookup` | 30 days | `treasurer_cache` |
| FEMA NFHL (flood zone) | `/flood-zone` | 1 year | `fema_cache` |
| AirNow (AQI) | `/aqi` | 1 hour | `aqi_cache` |
| RentCast (rent estimate) | `/rent` | 30 days | `rent_cache` |
| Google Places (amenities) | `/amenities` | 30 days | `amenities_cache` |
| Mapbox Directions (commute) | `/commute` | 30 days | `commute_cache` |
| HowLoud (noise score) | `/noise` | 1 year | `noise_cache` |
| Foursquare (vibe/POIs) | `/vibe` | 30 days | `amenities_cache` |
| Census Geocoder (address search) | `/geocode` | no cache — proxied through | — |

### Batch — pulled on a schedule, written to R2 bronze → Supabase silver

These run via Render crons through `orchestrator.py`. Nothing hits these APIs at query time.

| Source | Supabase Table | Schedule | Bronze in R2? |
|--------|---------------|----------|---------------|
| CPD crimes | `cpd_incidents` | Daily | ✅ |
| Chicago 311 violations | `complaints_311` | Daily | ✅ |
| Cook County Assessor | `buildings` | Monthly | ✅ |
| CTA GTFS stops | `cta_stops` | Quarterly | ✅ |
| Park District polygons | `parks` | Quarterly | ✅ |
| ACS rent data | `tracts` / `ccas` | Quarterly | ✅ |
| Streets | (streets table) | Quarterly | ✅ |

### One-shot loaders (run once manually, no cron)

| Source | Table | Bronze in R2? |
|--------|-------|---------------|
| UDP displacement typology | `displacement_typology` | ✅ |
| Chicago tract geometry | `tracts.geometry` | ✅ |
