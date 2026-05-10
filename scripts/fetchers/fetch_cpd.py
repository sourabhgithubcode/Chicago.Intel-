"""API #7 — Chicago Data Portal / CPD Crimes (Tier 3 pipeline).

Dataset: ijzp-q8t2 (Crimes 2001-present). Env: CHICAGO_DATA_TOKEN (optional;
without token, anonymous IP is throttled to 1K req/hr — fine for our quarterly
paginated pull).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sodapy import Socrata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transformers.cpd import to_silver
from utils.bronze_store import write_bronze

DOMAIN = "data.cityofchicago.org"
DATASET = "ijzp-q8t2"
TOKEN = os.getenv("CHICAGO_DATA_TOKEN")

PAGE_SIZE = 50_000           # Socrata's hard cap per request for this dataset
DATE_FLOOR = "2020-01-01"    # 5-year window for gold_address_intel violent/property counts


def fetch_all() -> list[dict]:
    """Page through CPD incidents from DATE_FLOOR forward."""
    client = Socrata(DOMAIN, TOKEN, timeout=60)
    rows: list[dict] = []
    offset = 0
    while True:
        chunk = client.get(
            DATASET,
            select="id,date,primary_type,latitude,longitude,iucr",
            where=f"latitude IS NOT NULL AND date >= '{DATE_FLOOR}'",
            limit=PAGE_SIZE,
            offset=offset,
        )
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def run(run_id: str) -> list[dict]:
    """Orchestrator entrypoint: fetch → bronze → silver-shaped rows."""
    raw = fetch_all()
    write_bronze("cpd", run_id, raw)
    return to_silver(raw)


if __name__ == "__main__":
    print(f"cpd: fetched {len(fetch_all())} rows")
