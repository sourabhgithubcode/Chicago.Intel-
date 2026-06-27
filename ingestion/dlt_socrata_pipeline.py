"""dlt ingestion showcase — Socrata (Chicago Data Portal) -> local DuckDB.

ADDITIVE demo. Independent of scripts/ — proves the dlt pattern:
  - @dlt.resource pages a SMALL slice of a Socrata REST dataset
  - incremental loading on the `date` cursor (only newer rows next run)
  - dlt auto-detects schema and loads to a local DuckDB file (no warehouse creds)
  - Loguru emits structured logs (console + JSON lines)

Default dataset: CPD Crimes ijzp-q8t2 (same source as scripts/fetchers/fetch_cpd.py).
Token: CHICAGO_DATA_TOKEN from .env (optional; anonymous works, just throttled).

Run:  .venv/bin/python ingestion/dlt_socrata_pipeline.py
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

import dlt
import requests
from dotenv import load_dotenv

from logging_setup import configure_logging

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
log = configure_logging()

DOMAIN = "data.cityofchicago.org"
DATASET = "ijzp-q8t2"               # CPD Crimes 2001-present
CURSOR_FIELD = "date"               # Socrata floating-timestamp used for incremental
INITIAL_CURSOR = "2024-01-01T00:00:00.000"
PAGE_SIZE = 1_000
MAX_ROWS = 3_000                    # keep the demo fast
TOKEN = os.getenv("CHICAGO_DATA_TOKEN")

DUCKDB_PATH = Path(__file__).resolve().parent / "chicago_ingest.duckdb"


@dlt.resource(name="cpd_crimes", write_disposition="append", primary_key="id")
def cpd_crimes(
    cursor=dlt.sources.incremental(CURSOR_FIELD, initial_value=INITIAL_CURSOR),
) -> Iterator[dict]:
    """Page CPD incidents from the Socrata REST endpoint, newest cursor forward.

    dlt's incremental tracks the max `date` seen; on the next run it resumes from
    there. We cap at MAX_ROWS so the showcase finishes in seconds.
    """
    url = f"https://{DOMAIN}/resource/{DATASET}.json"
    headers = {"X-App-Token": TOKEN} if TOKEN else {}
    start = cursor.last_value
    log.bind(dataset=DATASET, cursor_start=start).info("starting Socrata pull")

    offset = 0
    fetched = 0
    while fetched < MAX_ROWS:
        params = {
            "$select": "id,date,primary_type,latitude,longitude,iucr",
            "$where": f"date >= '{start}'",
            "$order": "date",
            "$limit": PAGE_SIZE,
            "$offset": offset,
        }
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        chunk = resp.json()
        if not chunk:
            break
        log.bind(offset=offset, rows=len(chunk)).debug("page fetched")
        yield from chunk
        fetched += len(chunk)
        if len(chunk) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    log.bind(dataset=DATASET, total_rows=fetched).info("Socrata pull complete")


def main() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="chicago_socrata",
        destination=dlt.destinations.duckdb(str(DUCKDB_PATH)),
        dataset_name="chicago_raw",
    )

    log.info("running dlt pipeline -> {}", DUCKDB_PATH.name)
    load_info = pipeline.run(cpd_crimes())
    log.bind(load_info=str(load_info)).info("load finished")

    # --- prove rows landed + show dlt's auto-detected schema -----------------
    with pipeline.sql_client() as client:
        with client.execute_query("SELECT COUNT(*) FROM cpd_crimes") as c:
            row_count = c.fetchone()[0]
        with client.execute_query(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'cpd_crimes' ORDER BY ordinal_position"
        ) as c:
            schema = c.fetchall()

    log.bind(table="cpd_crimes", rows=row_count).success("rows landed in DuckDB")
    log.info("auto-detected schema ({} columns):", len(schema))
    for col, dtype in schema:
        log.info("  {:<28} {}", col, dtype)


if __name__ == "__main__":
    main()
