# My Knowledge

---

## Design Rules

### Layout
- Two-column layout: left 50% scrollable data panel, right 50% fixed Mapbox map
- 4-layer breadcrumb navigation: **Chicago → CCA → Census Tract → Building**
- Building is always the default layer after address search (most granular)
- User zooms out via breadcrumb; breadcrumb levels are all clickable (back and forward)

### Color & Contrast
- Page canvas: `#EEF1F8` (light blue-grey)
- Card surface: `#FFFFFF`
- Text scale: `t0 #0F172A` / `t1 #1E293B` / `t2 #475569` / `t3 #64748B`
- Accent: `cyan #2563EB` (primary), `lime #16A34A` (verified), `amber #D97706` (signal), `rose #E11D48`
- All text must meet WCAG AA contrast on white (t3 = 4.6:1 minimum)

### Cards & Components
- `glass-1`: large container card (header), 16px radius, white, subtle shadow
- `glass-2`: section card (data blocks), 10px radius
- `glass-3`: inline badge / input / tag, `#F8FAFC` bg
- `label-mono`: Fira Code, 11px, uppercase, `#475569`, used for row labels and source tags
- `display`: Outfit 800, −0.02em tracking, used for section titles and big values
- Row dividers: `border-t border-slate-100` (never `border-white/5` — invisible on light bg)

### Icons
- Use `lucide-react` consistently throughout; no mixing icon libraries
- Section headers: 18px icon in `text-cyan` (or `text-amber` for risk sections)
- Row labels: 11px icon inline with label text via `flex items-center gap-1.5`
- ConfidenceTag: `ShieldCheck` (9-10/10 lime), `Shield` (7-8/10 cyan), `AlertTriangle` (≤6/10 amber)
- Breadcrumb levels: `Globe2` city / `Building` CCA / `Map` tract / `Building2` building

### Interactive States
- Active breadcrumb level: dark filled pill `bg-slate-900 text-white px-2.5 py-1 rounded-md`
- Inactive breadcrumb levels: `hover:bg-slate-100 hover:text-t0 active:bg-slate-200`
- Primary action button (Search): solid `bg-cyan text-white`, `hover:bg-blue-700`, `active:scale-95`
- Hover on any clickable element must produce visible feedback (bg or color change)
- All `details > summary` accordions: bg highlight on hover via global CSS

### Tooltips
- Black background (`bg-slate-900`), white text, 12px, max 220px wide, arrow pointer
- Trigger: dashed underline (`border-b border-dashed border-current`) + `cursor-help`
- Use for: technical terms (PIN, Census Tract, CCA, displacement typology, score definitions)
- Component: `src/components/Tooltip.jsx`

### Confidence System
- Every data point must carry a `ConfidenceTag` with score and source
- 9-10/10 → lime "verified" | 7-8/10 → cyan "strong" | ≤6/10 → amber "signal"
- Any score < 8/10 must have a "What this does not tell you" disclosure

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
