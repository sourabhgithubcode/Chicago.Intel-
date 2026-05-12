"""Chicago Data Portal — Building Permits (`ydr8-5enu`).

Bronze-only ingestion. Fills the §13.21 spec that was previously phantom.
Drives the construction-pipeline macro factor in §9.3.2 — `new_construction`
permits issued in the last 24 months at the polygon level signal supply.

Confidence: 9/10 — official City permit-of-record dataset.
Date floor: 2020-01-01 matches the §13.4 CPD 5-year pattern; covers the
24-month window for the macro factor plus ample backfill.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sodapy import Socrata

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.bronze_store import write_bronze

DOMAIN = "data.cityofchicago.org"
DATASET = "ydr8-5enu"
TOKEN = os.getenv("CHICAGO_DATA_TOKEN")

PAGE_SIZE = 50_000
DATE_FLOOR = "2020-01-01"


def fetch_all() -> list[dict]:
    client = Socrata(DOMAIN, TOKEN, timeout=120)
    rows: list[dict] = []
    offset = 0
    while True:
        chunk = client.get(
            DATASET,
            where=f"issue_date >= '{DATE_FLOOR}'",
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
    raw = fetch_all()
    write_bronze("building_permits", run_id, raw)
    return raw


if __name__ == "__main__":
    from datetime import datetime
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    rows = run(run_id)
    print(f"building_permits: {len(rows)} rows → bronze (run_id={run_id})")
