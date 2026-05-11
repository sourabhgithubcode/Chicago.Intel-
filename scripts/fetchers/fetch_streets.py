"""API #10 — Chicago Street Centerlines (Tier 3 pipeline, ArcGIS Feature Service).

The Chicago Data Portal's Socrata 6imu-meau endpoint is broken — both `.json`
and `.geojson` strip every property from the feature payload (rows come back
as `{}` with null geometry). The authoritative source is Chicago's own ArcGIS
server at gisapps.cityofchicago.org, same City IT shop, fully populated.

Source: gisapps.cityofchicago.org/.../ExternalApps/Centerline/MapServer/0
Confidence: 9/10 — official city centerline data, ~56K segments.

Field names on this layer are UPPERCASE (e.g. STREET_NAME, PRE_DIR, L_F_ADD,
STATUS). The transformer handles the mapping. Refresh annually.
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from transformers.streets import to_silver
from utils.bronze_store import write_bronze

LAYER = (
    "https://gisapps.cityofchicago.org/arcgis/rest/services/"
    "ExternalApps/Centerline/MapServer/0"
)
PAGE_SIZE = 2000  # maxRecordCount advertised by the layer


def fetch_all() -> list[dict]:
    """Page through the centerline layer, return raw GeoJSON features."""
    features: list[dict] = []
    offset = 0
    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "outSR": "4326",
            "f": "geojson",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
        }
        r = requests.get(f"{LAYER}/query", params=params, timeout=120)
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
    """Orchestrator entrypoint: fetch → bronze → silver-shaped rows."""
    raw = fetch_all()
    write_bronze("streets", run_id, raw)
    return to_silver(raw)


if __name__ == "__main__":
    feats = fetch_all()
    print(f"streets: {len(feats)} centerline features fetched")
