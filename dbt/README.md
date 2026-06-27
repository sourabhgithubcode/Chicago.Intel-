# Chicago.Intel — dbt GOLD layer (additive showcase)

This is an **additive** dbt project. It does **not** replace or modify the
production pipeline. The gold layer is owned today by
`supabase/migrations/006_gold_materialized_views.sql` (three
`MATERIALIZED VIEW`s refreshed by `refresh_gold_layer()`). This project
recreates that exact SQL as dbt models so the gold layer can be rebuilt,
tested, and documented by dbt once a Postgres connection exists.

Nothing in `scripts/` or `supabase/migrations/` was changed.

## Models

| dbt model | Mirrors (migration 006) | Materialization | Grain |
|-----------|-------------------------|-----------------|-------|
| `gold_address_intel` | `gold_address_intel` | table | one row per building (`pin`) |
| `gold_cca_summary` | `gold_cca_summary` | table | one row per Community Area (`id`) |
| `gold_tract_summary` | `gold_tract_summary` | table | one row per census tract (`id`) |

Silver tables are declared as dbt **sources** in
`models/staging/sources.yml` (schema `public`): `ccas`, `tracts`,
`buildings`, `cpd_incidents`, `complaints_311`, `cta_stops`, `parks`,
`displacement_typology`. dbt reads them; it never creates them.

### Tests (`models/gold/schema.yml`)
- `not_null` + `unique` on each key (`pin`, `id`).
- `dbt_utils.accepted_range` 0–10 on every score column; `>= 0` on counts.
- `relationships` from `cca_id` back to `ccas.id`.

## ⚠️ Why this cannot `dbt run` in this repo right now

dbt-postgres connects over the Postgres wire protocol and needs the
**database password**. This repo's `.env` only contains the Supabase REST
`SUPABASE_SERVICE_KEY` (a PostgREST/API key) — that is **not** a database
password and dbt cannot use it. So:

- ✅ `dbt parse` / `dbt compile` — work with no DB (validated, see below).
- ❌ `dbt run` / `dbt build` / `dbt test` — **blocked**: missing
  `SUPABASE_DB_PASSWORD`. Get it from Supabase dashboard →
  Project Settings → Database → Connection string, then set the env vars below.

## Run it (once you have the DB password)

```bash
# 1. install (or: pip install -r requirements.txt)
pip install dbt-postgres

# 2. connection — copy the template and point dbt at it
cp profiles.yml.template profiles.yml          # stays git-ignored
export DBT_PROFILES_DIR="$(pwd)"

# 3. set credentials (password is the one this repo does NOT have)
export SUPABASE_DB_HOST=aws-1-us-east-2.pooler.supabase.com
export SUPABASE_DB_PORT=5432
export SUPABASE_DB_NAME=postgres
export SUPABASE_DB_USER=postgres.ykbvjfpdqhpipxniwkqf
export SUPABASE_DB_PASSWORD=********           # <-- the missing piece

# 4. build + test
dbt deps          # installs dbt_utils
dbt build         # runs models, then runs schema.yml tests
```

## Validate without a database

```bash
dbt deps
dbt parse         # compiles + validates project, models, sources, tests — no DB
```

`dbt parse` was run in this session and **passed clean** (manifest written,
no errors). It compiles the Jinja/`ref()`/`source()` graph and all
`schema.yml` test definitions without ever opening a connection.
