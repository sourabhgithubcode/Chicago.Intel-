"""Chicago Data Portal — Parking Permit Zones (`u9xt-hiju`).

Bronze-only ingestion. Replaces the phantom `94t9-w7tc` "parking_lots" spec —
there is no Chicago Data Portal dataset for paid garage rates; permit zones
are what's actually publishable. Each row is a segment: ward + street +
address range + zone id (geometry is null on this dataset).

Confidence: 9/10 — official City of Chicago administrative boundary data.
Refresh: quarterly. Bronze write is the load-bearing artifact; silver lands
once the data-load freeze lifts.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.bronze_store import write_bronze

ENDPOINT = "https://data.cityofchicago.org/resource/u9xt-hiju.geojson"
PAGE_SIZE = 50_000  # dataset is ~10K rows; one page covers it


def fetch_all() -> list[dict]:
    headers = {}
    token = os.getenv("CHICAGO_DATA_TOKEN")
    if token:
        headers["X-App-Token"] = token

    features: list[dict] = []
    offset = 0
    while True:
        r = requests.get(
            ENDPOINT,
            params={"$limit": PAGE_SIZE, "$offset": offset},
            headers=headers,
            timeout=60,
        )
        r.raise_for_status()
        page = r.json().get("features") or []
        if not page:
            break
        features.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return features


def run(run_id: str) -> list[dict]:
    raw = fetch_all()
    write_bronze("parking_permit_zones", run_id, raw)
    return raw


if __name__ == "__main__":
    from datetime import datetime
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    rows = run(run_id)
    print(f"parking_permit_zones: {len(rows)} features → bronze (run_id={run_id})")
