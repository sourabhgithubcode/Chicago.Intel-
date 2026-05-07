"""Loader-level data integrity guards.

Three small helpers wired into scripts/loaders/__init__.py::load_all().
Spec: DATA_DICTIONARY.md §15.

Each helper either returns silently (pass) or raises ValidationError (fail).
A raised ValidationError aborts the orchestrator pass before gold refresh,
leaving silver in its prior state.
"""

import structlog

log = structlog.get_logger()

# Defaults — overridable per call.
DRIFT_THRESHOLD = 0.5      # fail if row count drops > 50% vs prior successful run
FAILURE_THRESHOLD = 0.10   # fail if > 10% of bronze rows didn't make it to silver


class ValidationError(Exception):
    """Raised when a loader-level invariant is violated."""


def assert_failure_rate(source: str, rows_in: int, rows_out: int,
                        threshold: float = FAILURE_THRESHOLD) -> None:
    """Bronze→silver drop rate guard.

    `rows_in`  = bronze row count (what the fetcher saw)
    `rows_out` = silver row count (what the transformer produced)

    Some drop is normal (Chicago bbox filter, missing PIN). Crossing the
    threshold means the transformer is broken or the source format shifted.
    """
    if rows_in == 0:
        return
    dropped = max(0, rows_in - rows_out)
    rate = dropped / rows_in
    if rate > threshold:
        raise ValidationError(
            f"{source}: {dropped}/{rows_in} rows dropped in transform "
            f"({rate:.1%} > {threshold:.0%}). Transformer or source schema may be broken."
        )
    log.info("failure_rate_ok", source=source, rows_in=rows_in,
             rows_out=rows_out, drop_rate=round(rate, 4))


def assert_row_count_drift(client, source: str, observed: int,
                           threshold: float = DRIFT_THRESHOLD) -> None:
    """Run-over-run row count guard.

    Compares `observed` to the most recent successful run's `rows_upserted`
    (per pipeline_runs, migration 011). A sudden drop usually means the
    source endpoint changed or auth broke.

    Skipped when no prior successful run exists (first run / seed).
    """
    res = (
        client.table("pipeline_runs")
        .select("rows_upserted")
        .eq("source", source)
        .eq("status", "success")
        .order("completed_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    if not rows or rows[0].get("rows_upserted") in (None, 0):
        return  # first run, nothing to compare against

    prior = rows[0]["rows_upserted"]
    if observed >= prior * (1 - threshold):
        log.info("row_count_drift_ok", source=source, prior=prior, observed=observed)
        return

    raise ValidationError(
        f"{source}: row count dropped from {prior} (last run) to {observed} "
        f"(>{int(threshold * 100)}% drop). Source endpoint or auth may have changed."
    )


def acquire_source_lock(client, source: str) -> None:
    """Acquire the per-source advisory lock (migration 013).

    Prevents two concurrent runs of the same source from racing. Lock is
    transaction-scoped server-side; raises if already held.
    """
    res = client.rpc("acquire_source_lock", {"p_source": source}).execute()
    got_it = bool(res.data) if res.data is not None else False
    if not got_it:
        raise ValidationError(
            f"{source}: another run is already holding the source lock. "
            f"Refusing to start a concurrent run."
        )
    log.info("source_lock_acquired", source=source)
