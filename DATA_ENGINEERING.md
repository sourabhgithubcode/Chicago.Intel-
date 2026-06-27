# Data-Engineering Tooling Showcases

These seven top-level directories demonstrate the project's data pipeline
implemented with a range of Python data-engineering libraries. They are
**additive and self-contained** — the production pipeline lives entirely in
`scripts/` and depends on **none** of them. Each showcase has its own
`requirements.txt` and is meant to run in its **own virtualenv** (the libraries
conflict with each other on shared pins — e.g. Airflow needs SQLAlchemy <2.0,
Prefect wants 2.0.x — so they cannot all share one env).

Where a showcase re-processes data, it reproduces the **exact output** of the
canonical transformer in `scripts/transformers/` (same row counts, same
classification), proving "same functionality."

| Dir | Libraries | What it does | Status |
|-----|-----------|--------------|--------|
| `spark/` | PySpark | CPD bronze→silver on 1.47M rows; `compare_with_transformer.py` asserts exact match | ✅ ran, exact match |
| `processing/` | Polars · DuckDB · PyArrow | CPD transform (Polars) + analytics (DuckDB) + Parquet (PyArrow) | ✅ ran, exact match |
| `ingestion/` | dlt · Loguru | Socrata→DuckDB incremental load + structured JSON logging | ✅ ran (3K rows, incremental) |
| `validation/` | Pydantic · Great Expectations | Schema validation of transformer output + GE suite on `ccas` | ✅ ran, all pass |
| `airflow/` | Apache Airflow | DAG wrapping the existing fetch→transform→score functions | ✅ DAG parses (0 errors) |
| `orchestration_extra/` | Prefect · Dask · SQLAlchemy | Prefect flow + Dask transform + SQLAlchemy ORM models | ✅ Prefect/Dask ran; SQLAlchemy needs DB password |
| `dbt/` | dbt-postgres | Gold-layer models + tests over the silver tables | ⚠️ `dbt parse` clean; `dbt run` needs DB password |

**Blocked items** (`dbt run`, SQLAlchemy connect) require a direct Postgres
connection string. This environment is **REST-only** (Supabase service key, no
DB password), so they are scaffolded and validated as far as the credentials
allow. **Paramiko** was intentionally skipped — the project has no SFTP source,
so a connector would be a pure stub.

Generated run-artifacts (`spark/out/`, `processing/out/`, `ingestion/*.duckdb`,
logs, dbt local state) are git-ignored — only source ships.
