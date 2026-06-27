"""
chicago_intel_pipeline — Apache Airflow showcase DAG (ADDITIVE).

This DAG does NOT reimplement the pipeline. It WRAPS the existing entrypoints
under ``scripts/`` and calls them from PythonOperator tasks:

    fetch_and_write_bronze   -> scripts/orchestrator.py::main()      (fetch + bronze write + pipeline_runs)
    bronze_to_silver         -> scripts/bronze_to_silver.py::run_source()
    validate_silver          -> scripts/utils/validation.py::assert_failure_rate()
    refresh_gold             -> scripts/scoring/*.compute() + RPC refresh_gold_layer()

Nothing in ``scripts/`` is modified. Imports of the pipeline modules happen
INSIDE the task callables (not at module top level) so DagBag parsing stays
light and never needs boto3/structlog/Supabase env vars just to import the DAG.

────────────────────────────────────────────────────────────────────────────
Render cron → single Airflow DAG mapping
────────────────────────────────────────────────────────────────────────────
render.yaml splits the real pipeline across THREE Render cron services, keyed
to how often each source actually publishes. This one DAG mirrors all three;
pick the source set per run via the ``sources`` param (or schedule three
copies, one per cadence). Default schedule here is @daily.

    Render cron name                     schedule         sources
    ───────────────────────────────────  ───────────────  ─────────────────────
    chicago-intel-pipeline-daily         0 9 * * *        cpd,311
    chicago-intel-pipeline-monthly       0 9 1 * *        assessor
    chicago-intel-pipeline-quarterly     0 9 1 */3 *      cta,parks,streets,acs

All three Render crons run with --bronze-only --skip-backup during the data
load freeze (memory: project_data_load_freeze.md). This DAG defaults to the
same bronze-only-safe posture: bronze_only=True, silver_dry_run=True,
enable_gold_refresh=False — so a run can never violate silver/gold invariants
until the per-source transformer cleaning is validated.

────────────────────────────────────────────────────────────────────────────
Standup
────────────────────────────────────────────────────────────────────────────
The pipeline modules need the repo's ``scripts/`` dir on sys.path and the same
env vars the Render crons use (SUPABASE_URL, SUPABASE_SERVICE_KEY, BRONZE_BUCKET,
R2_*, CHICAGO_DATA_TOKEN, COOK_COUNTY_TOKEN, CENSUS_API_KEY). orchestrator.py /
bronze_to_silver.py already load_dotenv() the repo-root ``.env`` themselves, so
running the Airflow scheduler from a shell that can read that .env is enough.
See airflow/README.md for exact commands.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pendulum

from airflow.decorators import task
from airflow.exceptions import AirflowSkipException
from airflow.models.dag import DAG
from airflow.models.param import Param

# Repo layout: <repo>/airflow/dags/this_file.py  ->  parents[2] == <repo>
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _ensure_scripts_on_path() -> None:
    """Put <repo>/scripts on sys.path so `import orchestrator`, `utils.*`,
    `transformers.*`, `scoring.*` resolve exactly as they do on Render.

    Done inside each task (not at import time) so DAG parsing never imports the
    heavy pipeline deps."""
    p = str(SCRIPTS_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)


default_args = {
    "owner": "chicago-intel",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="chicago_intel_pipeline",
    description="Wraps the existing Chicago.Intel data pipeline (fetch → bronze → silver → validate → gold).",
    default_args=default_args,
    # Real cadence is split across 3 Render crons (see header). @daily here is
    # the showcase default; drive the actual source set with the `sources` param.
    schedule="@daily",
    start_date=pendulum.datetime(2025, 1, 1, tz="America/Chicago"),
    catchup=False,
    max_active_runs=1,
    tags=["chicago-intel", "etl", "showcase"],
    params={
        # Comma-separated source list passed straight through to the existing
        # entrypoints. Default = the daily Render cron's set.
        "sources": Param("cpd,311", type="string"),
        # Bronze-only-safe defaults (data load freeze). Flip these only once
        # per-source transformer cleaning is validated.
        "bronze_only": Param(True, type="boolean"),
        "silver_dry_run": Param(True, type="boolean"),
        "enable_gold_refresh": Param(False, type="boolean"),
    },
) as dag:

    @task
    def fetch_and_write_bronze(**context) -> list[str]:
        """fetch_sources + write_bronze.

        Wraps scripts/orchestrator.py::main(). The orchestrator fetches each
        source via its run(run_id=...) function, writes the bronze archive, and
        (in --bronze-only mode) records a pipeline_runs row per source. We drive
        it exactly like the Render cron does — by setting argv and calling main()
        — so there is zero duplicated fetch/bronze logic here.
        """
        _ensure_scripts_on_path()
        import orchestrator  # scripts/orchestrator.py

        params = context["params"]
        sources = params["sources"]
        argv = ["orchestrator.py", "--sources", sources, "--skip-backup"]
        if params["bronze_only"]:
            argv.append("--bronze-only")

        saved = sys.argv
        try:
            sys.argv = argv
            # main() calls sys.exit(1) on any failure -> SystemExit -> task fails.
            orchestrator.main()
        finally:
            sys.argv = saved

        return [s.strip() for s in sources.split(",") if s.strip()]

    @task
    def bronze_to_silver(source_list: list[str], **context) -> dict:
        """Replay latest bronze → silver via scripts/bronze_to_silver.py.

        Calls run_source() per source — the exact function the manual replay CLI
        uses. dry_run defaults True (freeze): it downloads + transforms + counts
        rows but skips the Supabase upsert, so silver is never mutated until the
        transformer cleaning is signed off.
        """
        import os

        _ensure_scripts_on_path()
        import bronze_to_silver as b2s  # scripts/bronze_to_silver.py
        from utils.supabase_admin import get_admin_client

        params = context["params"]
        dry_run = bool(params["silver_dry_run"])

        # bronze_to_silver only knows its canonical source keys; the fetch step
        # may include sources without a transformer (skip those).
        known = [s for s in source_list if s in b2s.BRONZE_KEYS]

        s3_client = b2s._s3()
        bucket = os.environ["BRONZE_BUCKET"]
        supabase = None if dry_run else get_admin_client()

        stats: dict[str, dict] = {}
        for source in known:
            stats[source] = b2s.run_source(
                source, s3_client, bucket, supabase=supabase, dry_run=dry_run
            )
        return stats

    @task
    def validate_silver(stats: dict, **context) -> dict:
        """Gate the transform with the existing loader-level guard.

        Reuses scripts/utils/validation.py::assert_failure_rate — the same
        invariant load_all() enforces — on the bronze/silver counts run_source
        already produced. Raises ValidationError (fails the task) if any source
        dropped more than the allowed fraction of rows in transform.
        """
        _ensure_scripts_on_path()
        from utils.validation import assert_failure_rate

        for source, s in stats.items():
            assert_failure_rate(source, s["bronze_rows"], s["silver_rows"])
        return stats

    @task
    def refresh_gold(stats: dict, **context) -> None:
        """Recompute scores + refresh gold materialized views.

        Wraps scripts/scoring/*.compute() and the Postgres refresh_gold_layer()
        RPC (migration 006). Guarded by enable_gold_refresh — default False per
        the data load freeze, in which case the task is skipped, never run with
        stale/exploratory silver.
        """
        params = context["params"]
        if not params["enable_gold_refresh"]:
            raise AirflowSkipException(
                "enable_gold_refresh=False (data load freeze) — skipping score "
                "recompute + gold refresh."
            )

        _ensure_scripts_on_path()
        from scoring import safety, walk, landlord, displacement
        from utils.supabase_admin import get_admin_client

        # Each compute() reads silver, applies its documented formula, upserts.
        safety.compute()
        walk.compute()
        landlord.compute()
        displacement.compute()

        # Rebuild the gold layer the frontend reads (gold_address_intel, etc.).
        get_admin_client().rpc("refresh_gold_layer").execute()

    _sources = fetch_and_write_bronze()
    _stats = bronze_to_silver(_sources)
    _validated = validate_silver(_stats)
    refresh_gold(_validated)
