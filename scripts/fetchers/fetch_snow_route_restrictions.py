"""Chicago Data Portal — Snow Route Parking Restrictions (`i6k4-giaj`).

Bronze-only ingestion. 144 features, MultiLineString. Marks "Snow Route"
streets where parking is banned when 2"+ snow accumulates regardless of
time of year. Companion to §13.27 (Permit Zones) and Winter Overnight
(`mcad-r2g5`) for the "is street parking actually free?" question.

Confidence: 9/10 — official City of Chicago administrative data.
Refresh: annually.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.bronze_store import write_bronze

ENDPOINT = "https://data.cityofchicago.org/resource/i6k4-giaj.geojson"


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
    write_bronze("snow_route_restrictions", run_id, raw)
    return raw


if __name__ == "__main__":
    from datetime import datetime
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    rows = run(run_id)
    print(f"snow_route_restrictions: {len(rows)} features → bronze (run_id={run_id})")
