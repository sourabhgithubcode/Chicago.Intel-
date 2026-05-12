"""Chicago Data Portal — Winter Overnight Parking Restrictions (`mcad-r2g5`).

Bronze-only ingestion. Tiny dataset (20 features, MultiLineString). Marks the
arterial streets where parking is banned overnight from Dec 1 – Apr 1 regardless
of snowfall. Feeds the same "is street parking actually free?" question that
§13.27 (Parking Permit Zones) answers in a different dimension.

Confidence: 9/10 — official City of Chicago administrative data.
Refresh: annually (these designations rarely change).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.bronze_store import write_bronze

ENDPOINT = "https://data.cityofchicago.org/resource/mcad-r2g5.geojson"


def fetch_all() -> list[dict]:
    headers = {}
    token = os.getenv("CHICAGO_DATA_TOKEN")
    if token:
        headers["X-App-Token"] = token
    r = requests.get(ENDPOINT, params={"$limit": 50_000}, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json().get("features") or []


def run(run_id: str) -> list[dict]:
    raw = fetch_all()
    write_bronze("winter_overnight_restrictions", run_id, raw)
    return raw


if __name__ == "__main__":
    from datetime import datetime
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    rows = run(run_id)
    print(f"winter_overnight_restrictions: {len(rows)} features → bronze (run_id={run_id})")
