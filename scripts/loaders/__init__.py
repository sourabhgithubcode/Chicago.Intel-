"""
Silver + Gold loaders.

Bronze (raw JSONL) → Silver (normalized Postgres tables) → Gold (materialized views).

Each fetcher has already written bronze via scripts.utils.bronze_store.write_bronze().
This module upserts bronze rows into their silver tables, then refreshes
the gold materialized views in a single RPC call.

Integrity guards (DATA_DICTIONARY §15) run before each upsert:
  - acquire_source_lock      → no concurrent runs of the same source
  - assert_failure_rate      → fails if too many bronze rows dropped in transform
  - assert_row_count_drift   → fails if silver count drops sharply vs last run
"""
from __future__ import annotations

import structlog

from utils.validation import (
    acquire_source_lock,
    assert_failure_rate,
    assert_row_count_drift,
)

log = structlog.get_logger()


# Map fetcher source key → silver table name.
# Fetchers return a list[dict] already matching the silver schema.
SILVER_TABLE = {
    "acs":               "tracts",           # ACS also populates ccas (split handled in fetcher)
    "cpd":               "cpd_incidents",
    "assessor":          "buildings",
    "311":               "complaints_311",
    "cta":               "cta_stops",
    "parks":             "parks",
    "streets":           "streets",
    "treasurer":         "buildings",        # upsert enrichment onto buildings
}


def load_all(client, fetched: dict[str, list[dict]],
             rows_in_by_source: dict[str, int] | None = None):
    """
    Write each source's rows into its silver table via upsert,
    then refresh the gold layer once all silver loads succeed.

    `rows_in_by_source` is optional — bronze row count per source. When
    supplied, we run the bronze→silver failure-rate check (§15). Without
    it, that check is skipped (a fetcher that doesn't track bronze rows
    can still load).
    """
    rows_in_by_source = rows_in_by_source or {}

    for source, rows in fetched.items():
        table = SILVER_TABLE.get(source)
        if not table:
            log.warning("no_silver_mapping", source=source)
            continue
        if not rows:
            log.warning("no_rows_to_load", source=source)
            continue

        try:
            acquire_source_lock(client, source)

            rows_in = rows_in_by_source.get(source)
            if rows_in is not None:
                assert_failure_rate(source, rows_in=rows_in, rows_out=len(rows))

            assert_row_count_drift(client, source, observed=len(rows))

            client.table(table).upsert(rows).execute()
            log.info("silver_load_ok", source=source, table=table, rows=len(rows))
        except Exception as e:
            log.error("silver_load_failed", source=source, table=table, error=str(e))
            raise

    refresh_gold(client)


def refresh_gold(client):
    """Refresh all gold materialized views via the refresh_gold_layer() RPC."""
    try:
        client.rpc("refresh_gold_layer").execute()
        log.info("gold_refresh_ok")
    except Exception as e:
        log.error("gold_refresh_failed", error=str(e))
        raise
