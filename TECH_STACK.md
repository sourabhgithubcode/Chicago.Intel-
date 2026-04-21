# Chicago.Intel — Tech Stack

Final tech stack — every piece chosen for a specific reason, with what to avoid.

---

## The Stack

### Frontend

**React 18 + Vite**
- React because the ecosystem (Mapbox bindings, Supabase client, Tailwind) is mature
- Vite because build times are 10x faster than Create React App, and hot reload is instant
- Plain JavaScript (not TypeScript) for V2 — solo build, speed of iteration matters more than type safety right now. Add TS in V3 once the product is validated.

**Tailwind CSS**
- All the V1 styling is already Tailwind-friendly
- No separate CSS files to maintain
- Pairs well with shadcn/ui if you want prebuilt components later

**Mapbox GL JS + react-map-gl**
- Vector tiles render 77 polygons + 300K incident points smoothly
- `map.flyTo()` gives the V1 zoom animation
- `react-map-gl` wraps it cleanly for React
- 50K free map loads/month — more than enough for MVP

**Turf.js**
- Client-side geospatial calculations (radius queries, point-in-polygon)
- Used for the "is this click inside Lincoln Park?" type checks
- Also for the building polygon intersection with selected tract

### Backend / Database

**Supabase**
- PostgreSQL + PostGIS (essential for radius queries)
- Auto-generated REST API — no backend code to write
- Row Level Security for when you add user accounts later
- Realtime subscriptions if you ever need live updates
- Free tier: 500MB DB + 2GB bandwidth — handles MVP easily

**Supabase RPC Functions (PL/pgSQL)**
- The 4 core queries live as database functions
- `safety_at_point(lat, lng)`, `nearest_cta(lat, lng)`, etc.
- Called from frontend via `supabase.rpc('safety_at_point', {...})`
- Much faster than doing radius math client-side

### Hosting

**Render**
- Static site for the React frontend (free tier)
- Cron job for the Python data pipeline (free tier: 750 hr/mo)
- `render.yaml` gives infrastructure-as-code
- One dashboard for frontend + scheduled jobs

### Data Pipeline

**Python 3.11**
- For all the fetch_*.py scripts
- Nothing fancy — requests + pandas + sodapy for Socrata
- Runs on Render cron quarterly

**Specific Python packages:**
```
requests        # HTTP
pandas          # data wrangling
sodapy          # Chicago Data Portal API
geopandas       # GeoJSON handling for CCA/tract boundaries
psycopg2-binary # PostgreSQL driver
supabase        # official Supabase Python client
python-dotenv   # env var loading
```

### APIs

| API | Purpose | Cost |
|---|---|---|
| Google Maps Geocoding | Address → lat/lng | $5/1K after $200 free credit = ~28K free |
| Google Places | Amenity search + price_level | $17/1K after free credit = ~10K free |
| Mapbox | Base map tiles | 50K loads/mo free |
| FEMA NFHL | Flood zone lookup | Free |
| Census API | ACS rent data | Free with key |
| Chicago Data Portal (Socrata) | CPD, 311, etc. | Free with app token |
| Cook County Assessor | Bulk CSV download | Free |
| CTA GTFS | Transit stops | Free |

**Optional (V3):**
- Rentcast — $49/mo for live rent estimates
- HowLoud — $0.05/query for precise noise scores
- SpotHero API — parking rate lookups

### Dev Tooling

**Package manager: pnpm**
- 3x faster than npm
- Strict dependency resolution catches bugs earlier
- Smaller disk usage

**Version control: Git + GitHub**
- Render deploys on push to main
- GitHub Actions for lint/test in CI

**VS Code extensions (`.vscode/extensions.json`):**
- Prettier — auto-format
- Tailwind CSS IntelliSense — class autocomplete
- SQLTools + PostgreSQL driver — run queries against Supabase locally
- Python
- GitHub Copilot

**Analytics: GoatCounter**
- Privacy-respecting, lightweight
- Free for personal/non-commercial
- No cookie banner needed

---

## `package.json` — Exact Dependencies

```json
{
  "name": "chicago-intel",
  "version": "2.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "lint": "eslint src --ext .js,.jsx"
  },
  "dependencies": {
    "@supabase/supabase-js": "^2.39.0",
    "@turf/turf": "^6.5.0",
    "mapbox-gl": "^3.1.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-map-gl": "^7.1.6"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.1",
    "autoprefixer": "^10.4.17",
    "eslint": "^8.57.0",
    "eslint-plugin-react": "^7.33.2",
    "postcss": "^8.4.33",
    "prettier": "^3.2.4",
    "prettier-plugin-tailwindcss": "^0.5.11",
    "tailwindcss": "^3.4.1",
    "vite": "^5.0.12"
  }
}
```

## `requirements.txt` for Python

```
requests==2.31.0
pandas==2.2.0
geopandas==0.14.3
sodapy==2.2.0
psycopg2-binary==2.9.9
supabase==2.3.4
python-dotenv==1.0.1
shapely==2.0.2
```

---

## What to Deliberately NOT Use

**No Next.js** — No SSR needed. Static Vite build is faster, cheaper to host, and simpler to debug. Next.js is overkill for a data dashboard.

**No tRPC** — Supabase's auto-generated REST API + RPC functions give the same thing with zero extra code.

**No Prisma** — Supabase's client library handles queries cleanly. Prisma adds a migration system you'd duplicate with Supabase migrations.

**No Redux / Zustand / Jotai** — State is simple (selected address, salary, zoom level). React's `useState` + `useContext` is enough. Add state management only when a specific prop-drilling pain shows up.

**No shadcn/ui yet** — V1 already has a working design system. Don't rebuild it. Add shadcn in V3 if you want a component library.

**No Docker** — Render handles deploys. Not deploying to AWS. Docker adds complexity not needed here.

**No GraphQL** — Queries are straightforward CRUD. REST + RPC is faster to build and debug.

**No custom backend (Express, FastAPI)** — Supabase is the backend. Adding Node/Python servers between frontend and DB adds latency and another thing to deploy.

**No ORMs in Python scripts** — Raw SQL. Pipeline scripts are write-once, run-quarterly. An ORM's abstraction isn't worth it.

---

## The One-Sentence Version

**React + Vite + Tailwind + Mapbox on Render, talking to Supabase (PostgreSQL + PostGIS) via its auto-generated API, with Python pipelines on Render cron.**

Every piece is free at MVP scale, each piece is best-in-class for what it does, shippable solo in 5–7 weeks.

---

## Commit Discipline

```bash
# Every commit
git commit -m "week X: <what you shipped>"

# Every Friday
git push                    # triggers Render auto-deploy
# Check Render dashboard
# Check live URL
# Share URL with 1 person for feedback
```

Five Fridays. Five live updates. Week 5 the product answers Joe's challenge. Stack is done. Plan is done. Only thing left is the work.
