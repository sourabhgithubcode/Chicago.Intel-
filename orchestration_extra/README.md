# orchestration_extra — additive orchestration showcases

Three **additive** showcases that sit alongside the real pipeline. Nothing under
`scripts/` is modified — every runnable part imports and calls the existing
entrypoints. Install into the same venv that satisfies `scripts/requirements.txt`:

```bash
.venv/bin/pip install -r orchestration_extra/requirements.txt
```

| File | Tool | Status | Proof |
|---|---|---|---|
| `prefect_flow.py` | Prefect 2.x | **RUNS** (dry-run end-to-end) | 4 task runs Completed |
| `dask_transform.py` | Dask | **RUNS** (local scheduler) | matches `cpd.to_silver()` exactly |
| `sqlalchemy_models.py` | SQLAlchemy 2.x | **scaffold** — cannot connect | reports credential blocker |

---

## 1. `prefect_flow.py` — Prefect twin of the Airflow DAG

The Prefect version of `airflow/dags/chicago_intel_pipeline.py`. Same shape, same
bronze-only-safe defaults, same wrapping of the real entrypoints:

```
fetch_and_write_bronze → scripts/orchestrator.py::main()
bronze_to_silver       → scripts/bronze_to_silver.py::run_source()
validate_silver        → scripts/utils/validation.py::assert_failure_rate()
refresh_gold           → scripts/scoring/*.compute() + RPC refresh_gold_layer()
```

`dry_run=True` (default) stubs the two network-bound legs (orchestrator fetch +
R2 download) so the **whole DAG executes in seconds without touching prod** —
but the real validation gate still runs. Flip `dry_run=False` to run against R2 /
Supabase (still bronze-only-safe: `silver_dry_run=True`, `enable_gold_refresh=False`).

```bash
.venv/bin/python orchestration_extra/prefect_flow.py          # dry-run (proves DAG)
.venv/bin/python orchestration_extra/prefect_flow.py --wet    # real R2 + Supabase
```

Verified dry-run: `fetch_and_write_bronze → bronze_to_silver → validate_silver →
refresh_gold` all reached `Completed`, flow `Completed`. The validation task ran
the actual `scripts/utils/validation.py` guard (logged `failure_rate_ok`),
`refresh_gold` skipped per the data load freeze.

## 2. `dask_transform.py` — parallel CPD bronze→silver

Parallelizes the CPD transform (`classify_iucr` + Chicago bbox filter) across a
Dask bag on the local scheduler, dedups by id as a global reduction, then proves
parity against the canonical `scripts/transformers/cpd.py::to_silver()` on the
**same input**. It pulls a real CPD bronze sample from R2 (via the existing
`bronze_to_silver` helpers); if R2 is unreachable it falls back to a labeled
synthetic sample exercising every branch.

```bash
.venv/bin/python orchestration_extra/dask_transform.py                # R2 sample, 50k
.venv/bin/python orchestration_extra/dask_transform.py --limit 20000
.venv/bin/python orchestration_extra/dask_transform.py --synthetic    # offline
```

Verified against real R2 bronze (`bronze/cpd/…`, 20,000-row sample) — Dask and
`to_silver()` agree exactly:

| | dask | to_silver() |
|---|---:|---:|
| silver rows | 20,000 | 20,000 |
| violent | 1,921 | 1,921 |
| property | 6,044 | 6,044 |
| other | 12,035 | 12,035 |

`MATCH: PASS` (id sets equal, per-type counts equal).

## 3. `sqlalchemy_models.py` — ORM scaffold (cannot connect here)

SQLAlchemy 2.x typed ORM models for the four core silver tables (`buildings`,
`ccas`, `tracts`, `cpd_incidents`) + an engine factory.

**Blocker (same as dbt):** `.env` holds only `SUPABASE_SERVICE_KEY` — a REST /
PostgREST key. SQLAlchemy speaks the raw Postgres wire protocol (psycopg2) and
needs a direct DB password, which is **not present in this environment**. To run
it, add the Supabase pooler creds to `.env`:

```
SUPABASE_DB_HOST=aws-0-<region>.pooler.supabase.com
SUPABASE_DB_PORT=6543
SUPABASE_DB_NAME=postgres
SUPABASE_DB_USER=postgres.<project-ref>
SUPABASE_DB_PASSWORD=<your-db-password>   # the one secret missing here
```

```bash
.venv/bin/python orchestration_extra/sqlalchemy_models.py
```

The models import cleanly and `__main__` reports the missing-credential blocker
with no traceback (exit 0) — it only attempts a real connection once the vars
are set.

---

## Honest notes

- **Paramiko was intentionally skipped** — Chicago.Intel has no SFTP data source,
  so a Paramiko fetcher would be fake scaffolding (no caller). Not added.
- **SQLAlchemy version tension.** This scaffold needs SQLAlchemy 2.x; Prefect 2.20
  tolerates up to `2.0.35`, so the venv is pinned to **SQLAlchemy 2.0.35**. The
  separate `airflow/` showcase (Airflow 2.9.3) pins SQLAlchemy `<2.0` — the two
  orchestrators cannot share one venv at the SQLAlchemy major boundary. Run the
  Airflow showcase in its own venv if you need both.
- Secrets stay in `.env` (loaded via `python-dotenv`); none are committed.
