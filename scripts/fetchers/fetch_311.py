"""API #7 — Chicago Data Portal / 311 (Tier 3 pipeline).

Dataset: v6vf-nfxy (311 Service Requests). Env: CHICAGO_DATA_TOKEN (optional).
Pulls: building violations, heat complaints, bed bug reports, rodent reports.

NOTE: a previous version of this file pointed at kn9c-c2s2, which is the
'Selected Socioeconomic Indicators' dataset, not 311. Fixed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sodapy import Socrata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transformers._311 import to_silver
from utils.bronze_store import write_bronze

DOMAIN = "data.cityofchicago.org"
DATASET = "v6vf-nfxy"
TOKEN = os.getenv("CHICAGO_DATA_TOKEN")

PAGE_SIZE = 50_000
DATE_FLOOR = "2020-01-01"

RELEVANT_TYPES = (
    "Building Violation",
    "No Heat Complaint",
    "Bed Bug Complaint",
    "Rodent Baiting/Rat Complaint",
)


def fetch_all() -> list[dict]:
    client = Socrata(DOMAIN, TOKEN, timeout=60)
    type_filter = " OR ".join(f"sr_type='{t}'" for t in RELEVANT_TYPES)
    where = f"({type_filter}) AND latitude IS NOT NULL AND created_date >= '{DATE_FLOOR}'"

    rows: list[dict] = []
    offset = 0
    while True:
        chunk = client.get(DATASET, where=where, limit=PAGE_SIZE, offset=offset)
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def run(run_id: str) -> list[dict]:
    raw = fetch_all()
    write_bronze("311", run_id, raw)
    return to_silver(raw)


if __name__ == "__main__":
    print(f"311: fetched {len(fetch_all())} rows")
