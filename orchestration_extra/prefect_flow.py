"""
chicago_intel_pipeline — Prefect 2.x showcase flow (ADDITIVE).

The Prefect twin of airflow/dags/chicago_intel_pipeline.py. Same shape, same
guarantees, nothing under scripts/ is touched:

    fetch_and_write_bronze  -> scripts/orchestrator.py::main()
    bronze_to_silver        -> scripts/bronze_to_silver.py::run_source()
    validate_silver         -> scripts/utils/validation.py::assert_failure_rate()
    refresh_gold            -> scripts/scoring/{safety,walk,landlord,displacement}.compute()
                               + Postgres RPC refresh_gold_layer()

Like the Airflow DAG, the pipeline modules are imported INSIDE the tasks (not at
module top level) so the flow file imports cheaply and only needs boto3 /
Supabase env when it actually runs against prod.

────────────────────────────────────────────────────────────────────────────
dry_run — proving the DAG structure without touching prod
────────────────────────────────────────────────────────────────────────────
`dry_run=True` (the default) stubs the two heavy, network-bound legs — the
fetch+bronze write and the R2 download inside bronze_to_silver — so the flow
executes end to end in seconds and the task graph (fetch → silver → validate →
gold) is exercised for real, including the validation gate. It NEVER hits R2,
Supabase, or any source API in dry-run mode. Flip dry_run=False to run the real
pipeline (still bronze-only-safe: silver_dry_run=True, enable_gold_refresh=False
by default — see the data load freeze).

Run it:
    .venv/bin/python orchestration_extra/prefect_flow.py            # dry-run
    .venv/bin/python orchestration_extra/prefect_flow.py --wet      # real R2/Supabase
"""

from __future__ import annotations

import sys
from pathlib import Path

from prefect import flow, task, get_run_logger

# Repo layout: <repo>/orchestration_extra/this_file.py -> parents[1] == <repo>
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _ensure_scripts_on_path() -> None:
    """Put <repo>/scripts on sys.path so `import orchestrator`, `utils.*`,
    `transformers.*`, `scoring.*` resolve exactly as they do on Render."""
    p = str(SCRIPTS_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Tasks (thin wrappers over the existing entrypoints) ───────────────────────

@task(retries=2, retry_delay_seconds=5)
def fetch_and_write_bronze(sources: str, bronze_only: bool, dry_run: bool) -> list[str]:
    """Wraps scripts/orchestrator.py::main() — fetch + bronze write + pipeline_runs.

    dry_run short-circuits the network call but returns the same contract (the
    parsed source list) so every downstream task still runs.
    """
    log = get_run_logger()
    source_list = [s.strip() for s in sources.split(",") if s.strip()]

    if dry_run:
        log.info("[dry_run] skipping orchestrator.main(); sources=%s", source_list)
        return source_list

    _ensure_scripts_on_path()
    import orchestrator  # scripts/orchestrator.py

    argv = ["orchestrator.py", "--sources", sources, "--skip-backup"]
    if bronze_only:
        argv.append("--bronze-only")
    saved = sys.argv
    try:
        sys.argv = argv
        orchestrator.main()  # sys.exit(1) on failure -> SystemExit -> task fails
    finally:
        sys.argv = saved
    return source_list


@task(retries=1, retry_delay_seconds=5)
def bronze_to_silver(source_list: list[str], silver_dry_run: bool, dry_run: bool) -> dict:
    """Replay latest bronze → silver via scripts/bronze_to_silver.py::run_source().

    In flow dry_run mode we don't hit R2; we still import the real module and
    use its BRONZE_KEYS to filter to sources that actually have a transformer,
    then emit stub stats with the same {bronze_rows, silver_rows, dropped,
    table} shape run_source() returns, so validate_silver runs for real.
    """
    log = get_run_logger()
    _ensure_scripts_on_path()
    import bronze_to_silver as b2s  # scripts/bronze_to_silver.py

    known = [s for s in source_list if s in b2s.BRONZE_KEYS]
    skipped = [s for s in source_list if s not in b2s.BRONZE_KEYS]
    if skipped:
        log.info("no transformer for %s — skipping in silver step", skipped)

    if dry_run:
        # Stub stats: a small, in-threshold drop so validate_silver passes.
        stats = {
            s: {"bronze_rows": 1000, "silver_rows": 960, "dropped": 40,
                "table": b2s.SILVER_TABLE[s]}
            for s in known
        }
        log.info("[dry_run] stub silver stats: %s", stats)
        return stats

    import os
    from utils.supabase_admin import get_admin_client

    s3_client = b2s._s3()
    bucket = os.environ["BRONZE_BUCKET"]
    supabase = None if silver_dry_run else get_admin_client()

    stats: dict[str, dict] = {}
    for source in known:
        stats[source] = b2s.run_source(
            source, s3_client, bucket, supabase=supabase, dry_run=silver_dry_run
        )
    return stats


@task
def validate_silver(stats: dict) -> dict:
    """Gate with the existing loader invariant — runs identically in dry_run.

    Reuses scripts/utils/validation.py::assert_failure_rate (the same guard
    load_all() enforces). Raises ValidationError -> task fails -> gold never
    refreshes on a broken transform.
    """
    log = get_run_logger()
    _ensure_scripts_on_path()
    from utils.validation import assert_failure_rate

    for source, s in stats.items():
        assert_failure_rate(source, s["bronze_rows"], s["silver_rows"])
    log.info("validation passed for %s", list(stats))
    return stats


@task
def refresh_gold(stats: dict, enable_gold_refresh: bool, dry_run: bool) -> str:
    """Recompute scores + refresh gold MVs via scripts/scoring/*.compute().

    Guarded by enable_gold_refresh (default False per the data load freeze). When
    disabled — or in dry_run — the task returns a 'skipped' marker instead of
    touching scoring/Supabase, mirroring the Airflow AirflowSkipException branch.
    """
    log = get_run_logger()
    if not enable_gold_refresh or dry_run:
        reason = "dry_run" if dry_run else "enable_gold_refresh=False (data load freeze)"
        log.info("refresh_gold SKIPPED — %s", reason)
        return f"skipped:{reason}"

    _ensure_scripts_on_path()
    from scoring import safety, walk, landlord, displacement
    from utils.supabase_admin import get_admin_client

    safety.compute()
    walk.compute()
    landlord.compute()
    displacement.compute()
    get_admin_client().rpc("refresh_gold_layer").execute()
    log.info("gold layer refreshed")
    return "refreshed"


# ── Flow ──────────────────────────────────────────────────────────────────────

@flow(name="chicago_intel_pipeline")
def chicago_intel_pipeline(
    sources: str = "cpd,311",
    bronze_only: bool = True,
    silver_dry_run: bool = True,
    enable_gold_refresh: bool = False,
    dry_run: bool = True,
) -> dict:
    """fetch → bronze → silver → validate → gold, bronze-only-safe by default."""
    source_list = fetch_and_write_bronze(sources, bronze_only, dry_run)
    stats = bronze_to_silver(source_list, silver_dry_run, dry_run)
    validated = validate_silver(stats)
    gold_status = refresh_gold(validated, enable_gold_refresh, dry_run)
    return {"sources": source_list, "silver_stats": validated, "gold": gold_status}


if __name__ == "__main__":
    wet = "--wet" in sys.argv
    result = chicago_intel_pipeline(dry_run=not wet)
    print("\nflow result:", result)
