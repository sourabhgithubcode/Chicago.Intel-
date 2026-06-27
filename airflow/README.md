# Airflow showcase — `chicago_intel_pipeline`

An **additive** Apache Airflow DAG that orchestrates the existing
Chicago.Intel data pipeline. It does **not** reimplement anything: every task
is a thin `PythonOperator` wrapper around the real entrypoints in `scripts/`.

```
fetch_and_write_bronze  →  scripts/orchestrator.py::main()         (fetch + bronze write + pipeline_runs)
        │
bronze_to_silver        →  scripts/bronze_to_silver.py::run_source()
        │
validate_silver         →  scripts/utils/validation.py::assert_failure_rate()
        │
refresh_gold            →  scripts/scoring/{safety,walk,landlord,displacement}.compute()
                           + Postgres RPC refresh_gold_layer()  (migration 006)
```

Nothing under `scripts/` is modified. The pipeline modules are imported
**inside** the task callables, so DAG parsing never pulls in boto3 / geopandas /
Supabase env just to load the file.

## Render cron → this DAG

`render.yaml` runs the pipeline as three cron services. This one DAG mirrors all
three; choose the source set per run with the `sources` param.

| Render cron | schedule | `sources` |
|---|---|---|
| `chicago-intel-pipeline-daily` | `0 9 * * *` | `cpd,311` |
| `chicago-intel-pipeline-monthly` | `0 9 1 * *` | `assessor` |
| `chicago-intel-pipeline-quarterly` | `0 9 1 */3 *` | `cta,parks,streets,acs` |

The DAG's own `schedule` is `@daily` (showcase default).

## Params (bronze-only-safe defaults)

| param | default | effect |
|---|---|---|
| `sources` | `cpd,311` | comma-separated source list (passed straight to the entrypoints) |
| `bronze_only` | `True` | orchestrator stops after fetch + bronze write (no silver load) |
| `silver_dry_run` | `True` | `bronze_to_silver` transforms + counts but skips the upsert |
| `enable_gold_refresh` | `False` | `refresh_gold` is **skipped** (data load freeze) |

Defaults match the freeze (`memory: project_data_load_freeze.md`): a run can
fetch and validate transforms without ever mutating silver or gold.

## Standup / run

The tasks need `scripts/` on `sys.path` (the DAG adds it automatically) and the
same env vars the Render crons use:
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `BRONZE_BUCKET`, `R2_ENDPOINT`,
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `CHICAGO_DATA_TOKEN`,
`COOK_COUNTY_TOKEN`, `CENSUS_API_KEY`.
`orchestrator.py` and `bronze_to_silver.py` already `load_dotenv()` the
repo-root `.env`, so running the scheduler from a shell that can read that file
is enough. **Do not commit secrets** — keep them in `.env` / Airflow Variables.

```bash
# 1. install (same venv that satisfies scripts/requirements.txt)
.venv/bin/pip install -r scripts/requirements.txt
.venv/bin/pip install -r airflow/requirements.txt

# 2. point Airflow at this dags folder
export AIRFLOW_HOME="$PWD/.airflow"
export AIRFLOW__CORE__DAGS_FOLDER="$PWD/airflow/dags"
export AIRFLOW__CORE__LOAD_EXAMPLES=False

# 3. verify the DAG parses with no import errors
.venv/bin/python - <<'PY'
from airflow.models import DagBag
db = DagBag("airflow/dags", include_examples=False)
assert not db.import_errors, db.import_errors
print("OK:", list(db.dags))
PY

# 4. run it locally (standalone spins up scheduler + webserver + SQLite)
.venv/bin/airflow standalone
# …or trigger a single bronze-only-safe run from the CLI:
.venv/bin/airflow dags test chicago_intel_pipeline
```

To actually load silver / rebuild gold (only after transformer cleaning is
validated and the freeze is lifted), trigger with overridden params:

```bash
.venv/bin/airflow dags test chicago_intel_pipeline \
  -c '{"sources":"cpd,311","bronze_only":true,"silver_dry_run":false,"enable_gold_refresh":true}'
```
