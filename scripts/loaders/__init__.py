"""
Silver + Gold loaders.

Bronze (raw JSONL) → Silver (normalized Postgres tables) → Gold (materialized views).

Each fetcher has already written bronze via scripts.utils.bronze_store.write_bronze().
This module upserts bronze rows into their silver tables, then refreshes
the gold materialized views in a single RPC call.
"""

import structlog

log = structlog.get_logger()


# Map fetcher source key → silver table name.
# Fetchers return a list[dict] already matching the silver schema.
SILVER_TABLE = {
    "acs":       "tracts",           # ACS also populates ccas (split handled in fetcher)
    "cpd":       "cpd_incidents",
    "assessor":  "buildings",
    "311":       "complaints_311",
    "cta":       "cta_stops",
    "parks":     "parks",
    "treasurer": "buildings",        # upsert enrichment onto buildings
}


def load_all(client, fetched: dict[str, list[dict]]):
    """
    Write each source's rows into its silver table via upsert,
    then refresh the gold layer once all silver loads succeed.
    """
    for source, rows in fetched.items():
        table = SILVER_TABLE.get(source)
        if not table:
            log.warning("no_silver_mapping", source=source)
            continue
        if not rows:
            log.warning("no_rows_to_load", source=source)
            continue

        try:
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
