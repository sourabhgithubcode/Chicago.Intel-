"""Chicago Data Portal — CPS Elementary Attendance Boundaries (`5ihw-cbdn`).

Bronze-only ingestion. Replaces the phantom `8wkm-z37x` ID in the original
§13.24 spec — CPS publishes per-school-year datasets; `5ihw-cbdn` is the
current SY2425 elementary edition. Switches `school_elem` from
nearest-school approximation to point-in-polygon containment when silver
lands (confidence 7→9).

Confidence: 9/10 — official Chicago Public Schools boundary data.
Refresh: annually (new dataset ID per school year; update DATASET when
rolling forward).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.bronze_store import write_bronze

ENDPOINT = "https://data.cityofchicago.org/resource/5ihw-cbdn.geojson"


def fetch_all() -> list[dict]:
    headers = {}
    token = os.getenv("CHICAGO_DATA_TOKEN")
    if token:
        headers["X-App-Token"] = token
    r = requests.get(ENDPOINT, params={"$limit": 50_000}, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json().get("features") or []


def run(run_id: str) -> list[dict]:
    raw = fetch_all()
    write_bronze("cps_elementary_boundaries", run_id, raw)
    return raw


if __name__ == "__main__":
    from datetime import datetime
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    rows = run(run_id)
    print(f"cps_elementary_boundaries: {len(rows)} features → bronze (run_id={run_id})")
